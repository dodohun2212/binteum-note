"""F13 시험 대비 요약 노트: 자세한 정도, 강의 순서, AI 호출 5."""
import json
import re

from config import DIAG_MIN_PCT, ESSAY_MIN_PCT, NOTE_MAX_TOKENS
from core import llm, prompts
from core.cites import keep_pages, strip_bad_cites
from core.diagnose import evidence_pages
from core.extract import pages_text
from core.schemas import NoteSection

DETAILS = ("자세히", "보통", "짧게")
_LIMITS = {"자세히": (5, 2), "보통": (3, 1)}   # (핵심 개수, 자주 하는 실수 개수)
_POSITIVE = ("exam_hint", "emphasis", "mistake_warning", "exercise_hint")


def lecture_order(concepts: list, meta_pages) -> list:
    """강의 순서 = 개념이 본문(메타 페이지 제외)에 처음 나오는 쪽. 본문 쪽이 없으면 맨 뒤."""
    meta = set(meta_pages or [])

    def first_body(c):
        body = [p for p in c.get("pages") or [] if p not in meta]
        return min(body) if body else 10 ** 6

    ordered = sorted(enumerate(concepts), key=lambda ic: (first_body(ic[1]), ic[0]))
    return [c["id"] for _, c in ordered]


def detail_of(prio: dict) -> str:
    """자세한 정도는 코드가 정한다."""
    if (prio["action"] == "지금 당장" or prio["exam_pct"] >= ESSAY_MIN_PCT
            or (prio["status"] == "모름" and prio["exam_pct"] >= DIAG_MIN_PCT)):
        return "자세히"
    if prio["action"] == "다음" or prio["status"] == "헷갈림":
        return "보통"
    return "짧게"


def professor_quotes(concept_id: str, utterances: list, n: int = 3) -> list:
    """교수님 말은 AI가 아니라 코드가 호출 2 결과에서 강한 것부터 붙인다(같은 문장은 한 번)."""
    mine = [u for u in utterances or [] if u.get("concept_id") == concept_id]
    mine.sort(key=lambda u: (u["type"] not in _POSITIVE, -u["strength"]))
    out, seen = [], set()
    for u in mine:
        if u["quote"] in seen:
            continue
        seen.add(u["quote"])
        out.append({"quote": u["quote"], "type": u["type"], "strength": u["strength"]})
    return out[:n]


def short_note(concept: dict) -> dict:
    """'짧게'는 AI를 부르지 않고 호출 1의 한 줄 요약을 그대로 쓴다."""
    return NoteSection(concept_id=concept["id"], detail="짧게", from_ai=False,
                       summary=concept.get("summary") or concept["name"],
                       source_pages=[]).model_dump()


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def fix_recording_marks(text: str, quotes: list) -> str:
    """AI가 쓴 "(녹음)"은 그 문장에 교수님 말 목록의 인용이 실제로 있을 때만 남긴다."""
    text = text or ""
    if "(녹음)" not in text:
        return text
    keys = [_norm(q["quote"]).rstrip(".!?") for q in quotes or [] if q.get("quote")]
    out, pos = [], 0
    for m in re.finditer(r"\s?\(녹음\)", text):
        before = text[:m.start()]
        starts = [b.end() for b in re.finditer(r"[.!?]\s+|\n", before)]
        sentence = _norm(before[starts[-1] if starts else 0:])  # 표시가 붙은 그 문장
        out.append(text[pos:m.start()])
        if any(k and k in sentence for k in keys):
            out.append(m.group(0))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def clean_note(raw, concept: dict, detail: str, valid_pages, quotes: list = None) -> dict:
    if not isinstance(raw, dict):
        raise llm.BadJSONError("요약 노트가 객체가 아님")
    summary = strip_bad_cites(str(raw.get("summary") or "").strip(), valid_pages)
    if not summary:
        raise llm.BadJSONError("요약이 비어 있음")
    n_key, n_pit = _LIMITS.get(detail, (3, 1))

    def lines(key, limit):
        items = raw.get(key)
        if not isinstance(items, list):
            return []
        out = [fix_recording_marks(strip_bad_cites(str(v).strip(), valid_pages), quotes)
               for v in items if str(v or "").strip()]
        return out[:limit]

    pages = keep_pages(raw.get("source_pages"), valid_pages) or list(valid_pages)[:2]
    return NoteSection(concept_id=concept["id"], detail=detail, from_ai=True,
                       summary=fix_recording_marks(summary, quotes),
                       key_points=lines("key_points", n_key), pitfalls=lines("pitfalls", n_pit),
                       source_pages=pages).model_dump()


def note_prompt(concept: dict, detail: str, prio: dict, g, utterances: list, ptext: str) -> str:
    info = {
        "name": concept["name"], "detail": detail,
        "exam_score": prio["exam_pct"], "group": prio["action"], "status": prio["status"],
        "objective": concept.get("objective_quote"),
        "professor": professor_quotes(concept["id"], utterances, 5),
        "diagnosis": ({"score": g["score"], "error_type": g.get("error_type"), "reason": g.get("reason", "")}
                      if g else None),
    }
    return prompts.fill("05", CONCEPT_NAME=concept["name"], DETAIL=detail,
                        CONCEPT_JSON=json.dumps(info, ensure_ascii=False, indent=1), PAGES=ptext)


def make_note(concept: dict, prio: dict, g, utterances: list, material: dict, meta_pages, usage=None) -> dict:
    """개념 하나의 요약 노트. '짧게'는 AI를 부르지 않는다."""
    detail = detail_of(prio)
    if detail == "짧게":
        return short_note(concept)
    valid = evidence_pages(concept, meta_pages)
    text = note_prompt(concept, detail, prio, g, utterances, pages_text(material["pages"], valid))
    raw = llm.ask_json(text, NOTE_MAX_TOKENS, usage=usage)
    return clean_note(raw, concept, detail, valid, professor_quotes(concept["id"], utterances, 5))
