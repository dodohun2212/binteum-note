"""샘플 자료로 결과 예시(docs/결과_예시/)를 만든다. core/의 함수만 쓰고 앱과 같은 순서로 돈다.

    python scripts/make_example.py                 # 실제 AI (환경변수 또는 .streamlit/secrets.toml의 키)
    BINTM_FAKE_AI=1 python scripts/make_example.py # 가짜 AI로 모양만 확인
    python scripts/make_example.py --from-html 공부순서.html 요약노트.html   # 배포 앱에서 내려받은 파일로
"""
import argparse
import os
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from core import diagnose, explain, export, extract, llm, note, priority, sample  # noqa: E402
from core.html import kst_today  # noqa: E402

OUT_DIR = ROOT / "docs" / "결과_예시"
NAMES = ("공부순서_오답노트", "요약노트")


def load_key() -> None:
    """키는 환경변수 → .streamlit/secrets.toml 순으로 읽는다. 값은 출력하지 않는다."""
    if llm.is_fake() or os.environ.get("ANTHROPIC_API_KEY"):
        return
    path = ROOT / ".streamlit" / "secrets.toml"
    if path.exists():
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        llm.configure(data.get("ANTHROPIC_API_KEY"), data.get("OPENAI_API_KEY"))


class _ToMarkdown(HTMLParser):
    """내려받기 HTML → GitHub에서 읽기 좋은 마크다운."""

    HEAD = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.spans, self.divs = [], 0, [], []
        self.cell, self.row, self.table = None, None, None

    def emit(self, text: str) -> None:
        (self.cell if self.cell is not None else self.out).append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag in ("style", "script", "title"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag in self.HEAD:
            self.emit("\n\n" + self.HEAD[tag])
        elif tag in ("h5", "summary"):
            self.emit("\n\n**")
        elif tag == "p":
            self.emit("\n\n")
        elif tag == "br":
            self.emit("  \n")
        elif tag == "li":
            self.emit("\n- ")
        elif tag == "b":
            self.emit("**")
        elif tag == "img":
            self.emit("\n\n(그림) " + (a.get("alt") or "") + "\n\n")
        elif tag == "table":
            self.table = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []
        elif tag == "span":
            kind = "badge" if "bn-badge" in cls else "chip" if "bn-chip" in cls else ""
            self.emit("`" if kind == "badge" else "(" if kind == "chip" else "")
            self.spans.append(kind)
        elif tag == "div":
            kind = ""
            if "bn-box-t" in cls:
                kind = "bold"
                self.emit("\n\n**")
            elif "bn-fig-cap" in cls:
                self.emit("\n\n(그림) ")
            elif "bn-num-v" in cls:
                pass
            elif "bn-num-l" in cls:
                self.emit(" ")
            elif "bn-numrow" in cls:
                self.emit("\n\n")
            elif any(c in cls for c in ("bn-row", "bn-choice", "bn-num")):
                self.emit("\n- ")
            elif "bn-q" in cls:
                kind = "bold"
                self.emit("\n\n**")
            elif cls:
                self.emit("\n\n")
            self.divs.append(kind)

    def handle_endtag(self, tag):
        if tag in ("style", "script", "title"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("h5", "summary", "b"):
            self.emit("**")
        elif tag == "span" and self.spans:
            kind = self.spans.pop()
            self.emit("` " if kind == "badge" else ")" if kind == "chip" else " ")
        elif tag == "div" and self.divs:
            if self.divs.pop() == "bold":
                self.emit("**")
        elif tag in ("td", "th") and self.cell is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "/")
            self.cell = None
            if self.row is not None:
                self.row.append(text)
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            rows, self.table = self.table, None
            if rows:
                width = max(len(r) for r in rows)
                lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
                lines.insert(1, "|" + "---|" * width)
                self.emit("\n\n" + "\n".join(lines) + "\n\n")

    def handle_data(self, data):
        if not self.skip:
            self.emit(data)


def html_to_md(html_text: str) -> str:
    parser = _ToMarkdown()
    parser.feed(html_text)
    text = "".join(parser.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+(?=\S)", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\(p\.(\d+)\)\(p\.", r"(p.\1, p.", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def pipeline() -> tuple:
    """샘플 → 진단(섞어서) → 예시 답 → 채점 → 우선순위 → 자동 보완 설명 → 요약 노트. (state, stats)"""
    usage, times = llm.Usage(), {}
    data, transcript = sample.load_sample()
    material = extract.extract(sample.SAMPLE_PDF.name, data)
    saved = sample.saved_analysis(material, transcript)   # 앱의 샘플 체험과 같이 저장된 분석 결과
    concepts, meta, utts = saved["concepts"], saved["meta_pages"], saved["utterances"]
    scores = saved["scores"]["scores"]
    cmap = {c["id"]: c for c in concepts}
    pct = {r["concept_id"]: r["pct"] for r in scores}

    ids = diagnose.diag_targets(scores)
    names = [cmap[cid]["name"] for cid in ids]
    started = time.time()
    questions, errors, used = llm.run_many(
        {cid: (lambda u, cid=cid: diagnose.make_question(
            cmap[cid], diagnose.question_kind(pct[cid], "섞어서"), material, meta, names, u)) for cid in ids}, 6)
    usage.merge(used)
    times["문제 만들기"] = time.time() - started
    failed = {"문제": len(errors)}

    given = diagnose.example_answers(questions)
    grading, jobs = {}, {}
    for cid, q in questions.items():
        g = diagnose.grade_without_ai(q, given[cid]["answer"], given[cid]["dont_know"],
                                      given[cid]["choice"], given[cid]["guessed"])
        if g is None:
            jobs[cid] = (lambda u, cid=cid: diagnose.grade_essay(
                cmap[cid], questions[cid], given[cid]["answer"], material, meta, u))
        else:
            grading[cid] = g
    started = time.time()
    graded, errors, used = llm.run_many(jobs, 6)
    usage.merge(used)
    grading.update(graded)
    times["채점"] = time.time() - started
    failed["채점"] = len(errors)

    prios = priority.compute_priorities(scores, grading)
    prio_by = {p["concept_id"]: p for p in prios}
    confusion = {cid: g["confusion"] for cid, g in given.items() if g["confusion"]}
    started = time.time()
    explanations, errors, used = llm.run_many(
        {cid: (lambda u, cid=cid: explain.make_explanation(
            cmap[cid], prio_by[cid]["status"], questions.get(cid), grading.get(cid), given.get(cid),
            confusion.get(cid, ""), material, meta, u)) for cid in priority.auto_explain_ids(prios, confusion)}, 8)
    usage.merge(used)
    times["보완 설명"] = time.time() - started
    failed["보완 설명"] = len(errors)

    started = time.time()
    notes, errors, used = llm.run_many(
        {c["id"]: (lambda u, c=c: note.make_note(c, prio_by[c["id"]], grading.get(c["id"]), utts,
                                                 material, meta, u)) for c in concepts}, 8)
    usage.merge(used)
    times["요약 노트"] = time.time() - started
    failed["요약 노트"] = len(errors)

    state = {"material_name": material["name"], "has_transcript": True, "concepts": concepts,
             "meta_pages": meta, "utterances": utts, "scores": scores, "priorities": prios,
             "questions": questions, "given": given, "confusion": confusion, "grading": grading,
             "explanations": explanations, "notes": notes}
    status = {s: sum(1 for g in grading.values() if g["status"] == s) for s in ("앎", "헷갈림", "모름")}
    stats = {"concepts": len(concepts), "questions": len(questions), "status": status,
             "explanations": len(explanations),
             "details": {d: sum(1 for n in notes.values() if n["detail"] == d) for d in note.DETAILS},
             "times": times, "usage": usage, "failed": failed}
    return state, stats


def _readme(stats=None, from_html: bool = False) -> str:
    lines = ["# 결과 예시", "",
             "앱을 열지 않고도 결과를 읽을 수 있게, 샘플 자료(가상 자료구조 8장)로 만든 내려받기 파일이에요.", "",
             f"- [공부 순서·오답노트 (마크다운)]({NAMES[0]}.md) · [HTML]({NAMES[0]}.html)",
             f"- [시험 대비 요약 노트 (마크다운)]({NAMES[1]}.md) · [HTML]({NAMES[1]}.html)", "",
             f"- 만든 날: {kst_today().isoformat()} (한국 시간)"]
    if from_html:
        lines += ["- 만든 방법: 배포 앱에서 샘플 체험을 끝까지 돌려 ④에서 내려받은 HTML 2개를 그대로 넣고, "
                  "`python scripts/make_example.py --from-html`로 마크다운을 만들었어요."]
    elif stats:
        usage, status = stats["usage"], stats["status"]
        mode = "가짜 AI(모양 확인용)" if llm.is_fake() else config.LLM_MODEL
        lines += [f"- 만든 방법: `python scripts/make_example.py` (앱과 같은 순서: 샘플 → 진단(섞어서) → 예시 답 → 채점 → 공부 순서 → 요약 노트)",
                  f"- 모델: {mode}",
                  f"- 개념 {stats['concepts']}개, 진단 문제 {stats['questions']}개 "
                  f"(앎 {status['앎']} · 헷갈림 {status['헷갈림']} · 모름 {status['모름']})",
                  f"- 보완 설명 {stats['explanations']}개, 요약 노트 자세히 {stats['details']['자세히']} · "
                  f"보통 {stats['details']['보통']} · 짧게 {stats['details']['짧게']}",
                  "- 단계별 시간: " + " · ".join(f"{k} {v:.1f}초" for k, v in stats["times"].items())
                  + f" (합계 {sum(stats['times'].values()):.1f}초)",
                  f"- AI 호출 {usage.calls}번, 입력 {usage.input_tokens:,} · 출력 {usage.output_tokens:,} 토큰",
                  "- 실패: " + " · ".join(f"{k} {v}" for k, v in stats["failed"].items())]
    lines += ["", "샘플의 개념 추출·강조 발화는 앱의 샘플 체험과 같이 저장해 둔 결과(`tests/fixtures/`)를 썼어요.",
              "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다.", ""]
    return "\n".join(lines)


def write_files(out_dir: Path, study: str, notes: str, readme: str) -> list:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {f"{NAMES[0]}.html": study, f"{NAMES[1]}.html": notes,
             f"{NAMES[0]}.md": html_to_md(study), f"{NAMES[1]}.md": html_to_md(notes), "README.md": readme}
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    return sorted(files)


def run(out_dir=OUT_DIR) -> dict:
    """결과 예시 파일 5개를 쓰고 잰 값을 돌려준다."""
    state, stats = pipeline()
    stats["files"] = write_files(Path(out_dir), export.study_html(state), export.notes_html(state), _readme(stats))
    return stats


def from_html(study_path, notes_path, out_dir=OUT_DIR) -> list:
    """배포 앱에서 내려받은 HTML 2개로 마크다운과 README를 만든다."""
    study = Path(study_path).read_text(encoding="utf-8")
    notes = Path(notes_path).read_text(encoding="utf-8")
    return write_files(Path(out_dir), study, notes, _readme(from_html=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="샘플로 결과 예시 만들기")
    parser.add_argument("--from-html", nargs=2, metavar=("공부순서.html", "요약노트.html"))
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    if args.from_html:
        print("만든 파일:", from_html(args.from_html[0], args.from_html[1], args.out))
        return
    load_key()
    if not llm.has_key():
        print("키가 없어요. 환경변수 ANTHROPIC_API_KEY 또는 .streamlit/secrets.toml을 준비해 주세요.")
        sys.exit(1)
    stats = run(args.out)
    usage = stats["usage"]
    print("만든 파일:", stats["files"])
    print("상태:", stats["status"], "· 설명", stats["explanations"], "· 노트", stats["details"])
    print("시간:", {k: round(v, 1) for k, v in stats["times"].items()}, "합계", round(sum(stats["times"].values()), 1))
    print(f"호출 {usage.calls}번, 입력 {usage.input_tokens} · 출력 {usage.output_tokens} 토큰, 실패 {stats['failed']}")


if __name__ == "__main__":
    main()
