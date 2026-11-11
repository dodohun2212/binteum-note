"""F09 보완 설명 (AI 호출 4) + 페이지 검사."""
import json

from config import AI_MAX_TOKENS
from core import figure, llm, prompts
from core.cites import keep_pages, strip_bad_cites
from core.diagnose import MCQ, clean_answer, clean_confusion, evidence_pages
from core.extract import pages_text
from core.html import mark
from core.schemas import Explanation

NO_CONFUSION = "(없음)"
GAP_NOT_CHECKED = "아직 확인하지 않은 개념이다."
GAP_NO_ANSWER = "문제에 답하지 못했다. 문제가 물은 내용을 처음부터 확인해야 한다."
GAP_WRONG = "진단 문제에서 틀리거나 빠뜨린 부분이 있다."


def diagnosis_json(name: str, status: str, q=None, g=None, given=None) -> dict:
    """호출 4의 <diagnosis>: 문제 글, 그림(글로), 정답·모범 답안, 학생 답이 모두 들어간다."""
    d = {"concept": name, "status": status}
    if not q or not g:
        return d
    given = given or {}
    d.update(kind=q["kind"], question=q["question"], score=g["score"],
             error_type=g.get("error_type"), reason=g.get("reason", ""))
    if q.get("figure"):
        d["figure"] = figure.to_text(q["figure"])
    if q["kind"] == MCQ:
        choice = given.get("choice")
        d["choices"] = [f"{mark(i)} {c}" for i, c in enumerate(q["choices"])]
        d["correct"] = f"{mark(q['answer_index'])} {q['answer']}"
        if choice == -1:
            d["student_choice"] = "모르겠어요"
        elif isinstance(choice, int) and 0 <= choice <= 3:
            d["student_choice"] = f"{mark(choice)} {q['choices'][choice]}" + (
                " (확신 없이 고름)" if given.get("guessed") else "")
        else:
            d["student_choice"] = "(고르지 않음)"
    else:
        d["model_answer"] = q["answer"]
        d["rubric"] = q.get("rubric", [])
        if given.get("dont_know"):
            d["student_answer"] = "(모르겠어요)"
        else:
            d["student_answer"] = clean_answer(given.get("answer")) or "(빈 답)"
    return d


def fix_gap(my_gap: str, g=None) -> str:
    """'내가 놓친 점'이 진단 결과와 맞지 않으면 채점 이유에 맞는 말로 바꾼다."""
    gap = str(my_gap or "").strip()
    if g is None:  # 진단 안 함
        return gap or GAP_NOT_CHECKED
    if gap and "아직 확인하지 않은" not in gap:
        return gap  # AI의 구체적인 문장은 그대로
    if g.get("error_type") == "무응답":
        return GAP_NO_ANSWER
    return GAP_WRONG


def clean_explanation(raw, concept_id: str, valid_pages, confusion: str = "", g=None) -> dict:
    if not isinstance(raw, dict):
        raise llm.BadJSONError("설명이 객체가 아님")
    body = strip_bad_cites(str(raw.get("explanation") or "").strip(), valid_pages)
    if not body:
        raise llm.BadJSONError("설명이 비어 있음")
    reply = raw.get("confusion_reply")
    if not confusion or reply in (None, "", "null"):
        reply = None  # 적은 게 없으면 AI가 답을 써도 버린다
    else:
        reply = strip_bad_cites(str(reply).strip(), valid_pages) or None
    note = raw.get("not_found_note")
    not_found = raw.get("not_found") is True or str(raw.get("not_found")).lower() == "true"
    return Explanation(
        concept_id=concept_id, my_gap=fix_gap(raw.get("my_gap"), g), explanation=body,
        check_pages=keep_pages(raw.get("check_pages"), valid_pages)[:4],
        source_pages=keep_pages(raw.get("source_pages"), valid_pages),
        not_found=not_found,
        not_found_note=str(note).strip() if not_found and note not in (None, "", "null") else None,
        confusion_reply=reply,
    ).model_dump()


def explain_prompt(name: str, status: str, q, g, given, confusion: str, ptext: str) -> str:
    return prompts.fill(
        "04", CONCEPT_NAME=name,
        DIAGNOSIS_JSON=json.dumps(diagnosis_json(name, status, q, g, given), ensure_ascii=False, indent=1),
        CONFUSION=confusion or NO_CONFUSION, PAGES=ptext)


def make_explanation(concept: dict, status: str, q, g, given, confusion, material: dict,
                     meta_pages, usage=None) -> dict:
    """개념 하나의 보완 설명. 그 개념의 근거 쪽 텍스트만 보낸다."""
    valid = evidence_pages(concept, meta_pages)
    conf = clean_confusion(confusion)
    text = explain_prompt(concept["name"], status, q, g, given, conf,
                          pages_text(material["pages"], valid))
    raw = llm.ask_json(text, AI_MAX_TOKENS, usage=usage)
    return clean_explanation(raw, concept["id"], valid, conf, g)
