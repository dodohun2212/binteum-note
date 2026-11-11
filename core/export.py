"""F10 HTML 결과 파일 두 개: study_html(공부 순서·오답노트), notes_html(요약 노트).

외부 호출이 없는 순수 함수다. 페이지 그림은 넣지 않고, 글은 모두 이스케이프한다.
카드 조각(review_html 등)은 화면(screens)도 같이 쓴다.
"""
from core import figure
from core import score as score_mod
from core.diagnose import MCQ
from core.html import (BASE_CSS, NO_EXPLAIN_HINT, NOT_FOUND_LABEL, NOT_FOUND_TIP, NOTICE, NOTICE_END,
                       badge, bar, box, esc, kst_today, mark, numrow, page_chips, paragraphs, rich,
                       status_badge)
from core.note import DETAILS, lecture_order, professor_quotes
from core.priority import ACTIONS

ACTION_HINT = {
    "지금 당장": "여기부터 보세요. 시험에 나올 가능성이 높은데 아직 모르는 개념이에요.",
    "다음": "'지금 당장'을 끝낸 뒤에 보세요.",
    "복습만": "이미 알거나 출제 가능성이 낮은 개념이에요. 시간이 남으면 훑어보세요.",
}
FORMULA = "우선순위 = 출제 가능성 점수 × (1 − 이해도). 이해도는 앎 1.0 · 헷갈림 0.5 · 모름 0.0 · 진단 안 함 0.5예요."

DOC_CSS = """
body{font-family:-apple-system,'Segoe UI','Malgun Gothic','Apple SD Gothic Neo',sans-serif;font-size:17px;
  line-height:1.75;color:#111827;background:#f8fafc;margin:0}
main{max-width:860px;margin:0 auto;padding:22px 16px 60px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.25rem;margin:1.6em 0 .4em;border-bottom:2px solid #2563eb;padding-bottom:4px}
h3{font-size:1.08rem;margin:1.1em 0 .2em}h5{margin:.9em 0 .2em;font-size:1rem}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
ul{margin:.3em 0 .6em 1.2em;padding:0}
@media (prefers-color-scheme: dark){body{background:#0f172a;color:#e5e7eb}.bn-small{color:#9ca3af}
  h2{border-color:#60a5fa}}
@media print{body{background:#fff}details{display:block}.bn-card{break-inside:avoid}}
"""


def file_names(now=None) -> tuple:
    """내려받는 파일 이름 두 개. 날짜는 한국 시간."""
    day = kst_today(now).isoformat()
    return f"빈틈노트_공부순서_오답노트_{day}.html", f"빈틈노트_요약노트_{day}.html"


def _doc(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)}</title><style>{BASE_CSS}{DOC_CSS}</style></head>"
            f"<body><main>{body}</main></body></html>")


def _head(title: str, state: dict, now=None) -> str:
    rec = "녹음·대본 포함" if state.get("has_transcript") else "녹음·대본 없음"
    name = state.get("material_name") or "자료 없음"
    return (f"<h1>{esc(title)}</h1><p class='bn-small'>{esc(name)} · {kst_today(now).isoformat()} · {rec}</p>"
            + box(f"<p>{esc(NOTICE)}</p>", "nf"))


def review_html(q: dict, g, given=None) -> str:
    """내 문제와 답 다시 보기: 문제·그림·내 답·채점·정답·해설(또는 모범 답안)."""
    given = given or {}
    parts = [f'<div class="bn-q">{esc(q["question"])}</div>', figure.to_html(q.get("figure"))]
    if q["kind"] == MCQ:
        choice = given.get("choice")
        for i, text in enumerate(q["choices"]):
            cls, tag = "bn-choice", ""
            if g is not None and i == q["answer_index"]:
                cls += " bn-choice-ok"
                tag = " ✔ 정답" + (" · 내 답" if choice == i else "")
                if choice == i and given.get("guessed"):
                    tag += " (확신 없이 고름)"
            elif choice == i:
                cls += " bn-choice-bad" if g is not None else ""
                tag = " ✘ 내 답" if g is not None else " ← 내 답"
            parts.append(f'<div class="{cls}">{mark(i)} {esc(text)}<b>{tag}</b></div>')
        if choice == -1:
            parts.append('<p class="bn-small">내 답: 모르겠어요</p>')
    else:
        mine = "모르겠어요" if given.get("dont_know") else (str(given.get("answer") or "").strip() or "(답 없음)")
        parts.append(box(f"<p>{esc(mine)}</p>", "ans", "내 답"))
    if g is not None:
        line = status_badge(g["status"]) + badge(f'{g["score"]}/10', "plain")
        if g.get("error_type"):
            line += badge(g["error_type"], "plain")
        parts.append(f"<p>{line} {rich(g.get('reason', ''))}</p>")
        if q["kind"] == MCQ:
            if q.get("explanation"):
                parts.append(box(paragraphs(q["explanation"]), "ok", "해설"))
        else:
            rubric = ""
            scores = g.get("rubric_scores") or []
            for i, r in enumerate(q.get("rubric") or []):
                got = f"{scores[i]}/" if i < len(scores) else ""
                rubric += f"<li>{esc(r['point'])} <span class='bn-small'>({got}{r['score']}점)</span></li>"
            parts.append(box(f"<p>{esc(q['answer'])}</p><ul>{rubric}</ul>", "ok", "모범 답안"))
        if q.get("source_pages"):
            parts.append(f"<p class='bn-small'>근거 페이지 {page_chips(q['source_pages'])}</p>")
    return "".join(parts)


def explanation_html(expl, confusion: str = "") -> str:
    """보완 설명: 내가 놓친 점, (적었으면) 내가 헷갈린 점과 그에 대한 답, 문단 설명, 찾지 못함, 다시 볼 페이지."""
    parts = []
    if expl and expl.get("my_gap"):
        parts.append(box(f"<p>{rich(expl['my_gap'])}</p>", "gap", "내가 놓친 점"))
    conf = str(confusion or "").strip()
    if conf:
        reply = expl.get("confusion_reply") if expl else None
        inner = f"<p class='bn-small'>내가 적은 글: {esc(conf)}</p>" + (paragraphs(reply) if reply else "")
        parts.append(box(inner, "reply", "💬 내가 헷갈린 점에 대한 답" if reply else "💬 내가 헷갈린 점"))
    if expl:
        parts.append(paragraphs(expl["explanation"]))
        if expl.get("not_found"):
            note = str(expl.get("not_found_note") or "").strip()
            if note and note[-1] not in ".!?":
                note += "."
            parts.append(box(f"<p><b>{NOT_FOUND_LABEL}</b> {esc(note)} {NOT_FOUND_TIP}</p>", "nf"))
        if expl.get("check_pages"):
            parts.append(f"<p class='bn-small'>다시 볼 페이지 {page_chips(expl['check_pages'])}</p>")
    return "".join(parts)


def note_body_html(note: dict, quotes: list = None) -> str:
    """요약 노트 한 절의 본문: 요약 문단, 핵심, 자주 하는 실수, 교수님 말, 근거 페이지."""
    parts = [paragraphs(note["summary"])]
    if note.get("key_points"):
        parts.append("<h5>핵심</h5><ul>" + "".join(f"<li>{rich(v)}</li>" for v in note["key_points"]) + "</ul>")
    if note.get("pitfalls"):
        parts.append("<h5>자주 하는 실수</h5><ul>" + "".join(f"<li>{rich(v)}</li>" for v in note["pitfalls"]) + "</ul>")
    if quotes:
        lines = "".join(f"<li>“{esc(u['quote'])}” <span class='bn-chip bn-rec'>녹음</span></li>" for u in quotes)
        parts.append(f"<h5>교수님 말</h5><ul>{lines}</ul>")
    if note.get("source_pages"):
        parts.append(f"<p class='bn-small'>근거 페이지 {page_chips(note['source_pages'])}</p>")
    return "".join(parts)


def _prio_badges(p: dict) -> str:
    return (status_badge(p["status"]) + badge(f"출제 점수 {p['exam_pct']}", "blue")
            + badge(f"우선순위 {p['priority']}", "plain"))


def _study_row(p: dict, score_row) -> str:
    reasons = ""
    if score_row:
        reasons = "".join(badge(t, "neg" if neg else "plain") for t, neg in score_mod.badges(score_row))
    return (f'<div class="bn-row"><span class="bn-row-rank">{p["rank"]}</span>'
            f'<span class="bn-row-name">{esc(p["name"])}</span>'
            f'<span class="bn-row-bar">{bar(p["exam_pct"])}</span>'
            f'<span class="bn-row-pct">{p["exam_pct"]}점</span>'
            f'<span class="bn-row-badges"><span class="bn-small">출제 가능성 점수 {p["exam_pct"]}점 · </span>'
            f"{_prio_badges(p)}{reasons}</span></div>")


def _wrong_card(p: dict, state: dict) -> str:
    cid = p["concept_id"]
    q, g = state["questions"][cid], state["grading"][cid]
    expl = (state.get("explanations") or {}).get(cid)
    conf = (state.get("confusion") or {}).get(cid, "")
    body = review_html(q, g, (state.get("given") or {}).get(cid))
    body += "<h5>보완 설명</h5>"
    if expl or str(conf).strip():
        body += explanation_html(expl, conf)
    if not expl:
        body += f"<p class='bn-small'>{esc(NO_EXPLAIN_HINT)}</p>"
    return (f'<div class="bn-card"><h4>{p["rank"]}. {esc(p["name"])}</h4>'
            f"<p>{_prio_badges(p)}{badge(q['kind'], 'plain')}</p>{body}</div>")


def study_html(state: dict, now=None) -> str:
    """① 공부 순서·오답노트 파일."""
    prios = state.get("priorities") or []
    grading = state.get("grading") or {}
    questions = state.get("questions") or {}
    score_by = {r["concept_id"]: r for r in state.get("scores") or []}
    out = [_head("빈틈노트 공부 순서·오답노트", state, now)]
    counts = {a: sum(1 for p in prios if p["action"] == a) for a in ACTIONS}
    out.append(numrow([("지금 당장", counts["지금 당장"], "bad"), ("다음", counts["다음"], "warn"),
                       ("복습만", counts["복습만"], "plain")]))

    out.append("<h2>1. 공부 순서</h2>")
    if not prios:
        out.append("<p>우선순위 없음</p>")
    for action in ACTIONS:
        group = [p for p in prios if p["action"] == action]
        if group:
            out.append(f"<h3>{action} · {len(group)}개</h3><p class='bn-small'>{ACTION_HINT[action]}</p>")
            out.extend(_study_row(p, score_by.get(p["concept_id"])) for p in group)
    if prios:
        out.append(f"<p class='bn-small'>{esc(FORMULA)}</p>")

    graded = [p for p in prios if p["concept_id"] in grading and p["concept_id"] in questions]
    wrong = [p for p in graded if p["status"] in ("모름", "헷갈림")]
    right = [p for p in graded if p["status"] == "앎"]
    out.append("<h2>2. 오답노트</h2>")
    if not graded:
        out.append("<p>진단하지 않음</p>")
    elif not wrong:
        out.append("<p>틀리거나 헷갈린 문제가 없어요.</p>")
    out.extend(_wrong_card(p, state) for p in wrong)

    out.append(f"<h2>3. 맞힌 문제 · {len(right)}개</h2>")
    for p in right:
        out.append(f"<details><summary>{p['rank']}. {esc(p['name'])}</summary>{_wrong_card(p, state)}</details>")

    extra = [p for p in prios if p["concept_id"] not in grading
             and p["concept_id"] in (state.get("explanations") or {})]
    if extra:
        out.append("<h2>4. 진단하지 않은 개념 설명</h2>")
        for p in extra:
            out.append(f'<div class="bn-card"><h4>{p["rank"]}. {esc(p["name"])}</h4><p>{_prio_badges(p)}</p>'
                       + explanation_html(state["explanations"][p["concept_id"]], "") + "</div>")
    out.append(f"<p class='bn-small'>{esc(NOTICE_END)}</p>")
    return _doc("빈틈노트 공부 순서·오답노트", "".join(out))


def note_card_html(concept: dict, note: dict, prio, utterances: list) -> str:
    badges = badge(note["detail"], "blue")
    small = ""
    if prio:
        badges += badge(f"출제 점수 {prio['exam_pct']}", "blue") + status_badge(prio["status"]) + badge(prio["action"], "plain")
        small = f"<p class='bn-small'>출제 가능성 점수 {prio['exam_pct']}점</p>"
    quotes = professor_quotes(concept["id"], utterances, 3)
    return (f'<div class="bn-card"><h4>{esc(concept["name"])}</h4><p>{badges}</p>{small}'
            f"{note_body_html(note, quotes)}</div>")


def notes_html(state: dict, now=None) -> str:
    """② 시험 대비 요약 노트 파일. 강의 순서대로."""
    notes = state.get("notes") or {}
    concepts = {c["id"]: c for c in state.get("concepts") or []}
    prio_by = {p["concept_id"]: p for p in state.get("priorities") or []}
    out = [_head("빈틈노트 시험 대비 요약 노트", state, now)]
    order = [cid for cid in lecture_order(list(concepts.values()), state.get("meta_pages")) if cid in notes]
    if not order:
        out.append("<p>요약 노트 없음</p>")
    else:
        counts = {d: sum(1 for cid in order if notes[cid]["detail"] == d) for d in DETAILS}
        out.append(numrow([(d, counts[d], "blue" if d == "자세히" else "plain") for d in DETAILS]))
        out.append("<p class='bn-small'>강의 순서대로 정리했어요. 중요한 개념일수록 자세히 썼어요.</p>")
        for cid in order:
            out.append(note_card_html(concepts[cid], notes[cid], prio_by.get(cid), state.get("utterances") or []))
    out.append(f"<p class='bn-small'>{esc(NOTICE_END)}</p>")
    return _doc("빈틈노트 시험 대비 요약 노트", "".join(out))
