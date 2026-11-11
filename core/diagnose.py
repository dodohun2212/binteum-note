"""F08 진단: 대상·문제 형식 고르기, 문제 만들기(03-A·03-C), 채점(03-B는 AI, 객관식은 코드)."""
import hashlib
import json
import random
import re

from config import (AI_MAX_TOKENS, CONFUSION_MAX_CHARS, DIAG_MIN_PCT, ESSAY_MIN_PCT,
                    MAX_EVIDENCE_PAGES, QUICK_DIAG_AUTO_OVER)
from core import figure, llm, prompts
from core.cites import keep_pages, strip_bad_cites
from core.extract import pages_text
from core.html import eul, ieyo
from core.schemas import Grading, Question

MODES = ("섞어서", "모두 객관식", "모두 서술형")
ESSAY, MCQ = "서술형", "객관식"
ERROR_TYPES = ("개념 혼동", "비교 방향 오류", "복잡도 오류", "절차 누락", "계산 실수", "무응답", "기타")
EXAMPLE_CONFUSION = "두 보기 사이에서 고민했어요. 둘이 어떻게 다른지 모르겠어요."

# 문제가 페이지·그림을 가리킬 때 덧붙이는 한 단락 (BR-10의 예외)
FIX_NOTE = (
    "## 다시 만들기\n"
    "방금 만든 문제는 문제 글에 페이지 번호가 있거나, figure 없이 그림·트리·표를 가리켰습니다. "
    "학생은 문제 화면만 봅니다. 페이지 번호를 쓰지 말고, 그림이 필요하면 작은 예를 figure에 넣어 "
    "문제를 처음부터 다시 만드세요."
)

REASON_DONT_KNOW = "'모르겠어요'를 골라 모름으로 표시했어요."
REASON_BLANK = "답을 비워 두어 모름으로 표시했어요."
REASON_NO_CHOICE = "보기를 고르지 않아 모름으로 표시했어요."


class QuestionFormatError(ValueError):
    """AI가 준 문제의 형식이 어긋남."""

    code = "E-08"
    message = "AI 답을 읽지 못했어요. 다시 시도해 주세요"


# ---------- 대상과 형식 ----------

def diag_targets(scores: list, top=None) -> list:
    """출제 점수 20점 이상 개념 전부(순위 순서). top을 주면 그중 상위 top개만(빠른 진단)."""
    ids = [r["concept_id"] for r in scores if r["pct"] >= DIAG_MIN_PCT]
    return ids[:top] if top else ids


def question_kind(pct: int, mode: str) -> str:
    if mode == "모두 객관식":
        return MCQ
    if mode == "모두 서술형":
        return ESSAY
    return ESSAY if pct >= ESSAY_MIN_PCT else MCQ


def quick_default(from_sample: bool, n_targets: int) -> bool:
    """빠른 진단 기본값: 직접 올린 자료이고 대상이 8개보다 많을 때만 켜짐."""
    return (not from_sample) and n_targets > QUICK_DIAG_AUTO_OVER


def evidence_pages(concept: dict, meta_pages) -> list:
    """그 개념의 근거 쪽. 8쪽을 넘으면 본문 쪽부터 8쪽만."""
    meta = set(meta_pages or [])
    pages = sorted(set(concept.get("pages") or []))
    if len(pages) > MAX_EVIDENCE_PAGES:
        body = [p for p in pages if p not in meta]
        rest = [p for p in pages if p in meta]
        pages = sorted((body + rest)[:MAX_EVIDENCE_PAGES])
    return pages


def others_text(names: list, own: str) -> str:
    """{{OTHER_CONCEPTS}} 자리: 함께 진단하는 다른 개념 이름(자기 이름은 뺀다)."""
    rest = [n for n in names if n != own]
    return "\n".join(f"- {n}" for n in rest) if rest else "(없음)"


# ---------- 문제 다듬기 ----------

_NUMBERING = re.compile(r"^\s*(?:[①②③④⑤]|\(?[1-5A-Ea-e가-라][.)]|\([1-5A-Ea-e]\))\s*")


def _fit_rubric(items: list) -> list:
    """루브릭 합이 10이 아니면 비례로 맞춘다."""
    total = sum(s for _, s in items)
    if total == 10:
        return [{"point": p, "score": s} for p, s in items]
    if total <= 0:
        base = [10 // len(items)] * len(items)
    else:
        base = [int(s * 10 / total) for _, s in items]
    i = 0
    while sum(base) < 10:
        base[i % len(base)] += 1
        i += 1
    return [{"point": p, "score": s} for (p, _), s in zip(items, base)]


def clean_essay(raw, valid_pages) -> dict:
    if not isinstance(raw, dict):
        raise QuestionFormatError("문제가 객체가 아님")
    question = str(raw.get("question") or "").strip()
    answer = str(raw.get("answer") or "").strip()
    rubric_raw = raw.get("rubric")
    if not question or not answer or not isinstance(rubric_raw, list):
        raise QuestionFormatError("문제·정답·루브릭 누락")
    items = []
    for r in rubric_raw:
        if not isinstance(r, dict) or not str(r.get("point") or "").strip():
            continue
        try:
            score = max(0, int(round(float(r.get("score", 0)))))
        except (TypeError, ValueError):
            score = 0
        items.append((str(r["point"]).strip(), score))
    if not items:
        raise QuestionFormatError("루브릭이 비어 있음")
    q = Question(kind=ESSAY, question=question, answer=answer, rubric=_fit_rubric(items),
                 source_pages=keep_pages(raw.get("source_pages"), valid_pages),
                 figure=figure.clean_figure(raw.get("figure")))
    return q.model_dump()


def clean_mcq(raw, valid_pages) -> dict:
    """03-C 답 검사 + 보기 섞기. 보기 4개가 서로 다르고 정답 위치가 0~3이어야 한다."""
    if not isinstance(raw, dict):
        raise QuestionFormatError("문제가 객체가 아님")
    question = str(raw.get("question") or "").strip()
    choices = raw.get("choices")
    if not question or not isinstance(choices, list) or len(choices) != 4:
        raise QuestionFormatError("문제 또는 보기 4개가 아님")
    choices = [_NUMBERING.sub("", str(c or "")).strip() for c in choices]
    if any(not c for c in choices) or len(set(choices)) != 4:
        raise QuestionFormatError("보기가 비었거나 겹침")
    idx = raw.get("answer_index")
    if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx <= 3:
        raise QuestionFormatError("정답 위치가 0~3이 아님")
    correct = choices[idx]
    # 문제마다 고정된 seed로 섞는다(AI가 정답을 한 자리에 몰아 두는 버릇 방지)
    seed = int(hashlib.md5(question.encode("utf-8")).hexdigest(), 16)
    order = list(range(4))
    random.Random(seed).shuffle(order)
    shuffled = [choices[i] for i in order]
    q = Question(kind=MCQ, question=question, answer=correct, choices=shuffled,
                 answer_index=shuffled.index(correct),
                 explanation=strip_bad_cites(str(raw.get("explanation") or "").strip(), valid_pages),
                 source_pages=keep_pages(raw.get("source_pages"), valid_pages),
                 figure=figure.clean_figure(raw.get("figure")))
    return q.model_dump()


# ---------- 문제 만들기 ----------

def _generate(kind, name, ptext, valid, others, usage, fix=False) -> dict:
    text = prompts.fill("03C" if kind == MCQ else "03A", CONCEPT_NAME=name,
                        OTHER_CONCEPTS=others, PAGES=ptext)
    if fix:
        text += "\n\n" + FIX_NOTE
    raw = llm.ask_json(text, AI_MAX_TOKENS, usage=usage)
    return clean_mcq(raw, valid) if kind == MCQ else clean_essay(raw, valid)


def _make_mcq(name, ptext, valid, others, usage) -> dict:
    q = _generate(MCQ, name, ptext, valid, others, usage)
    if figure.points_to_missing(q["question"], q["figure"]):
        q = _generate(MCQ, name, ptext, valid, others, usage, fix=True)
        if figure.points_to_missing(q["question"], q["figure"]):
            raise QuestionFormatError("객관식이 두 번 다 페이지·그림을 가리킴")
    return q


def _make_essay(name, ptext, valid, others, usage) -> dict:
    """개념마다 2번까지 시도한다."""
    kept, last, fix = None, None, False
    for _ in range(2):
        try:
            q = _generate(ESSAY, name, ptext, valid, others, usage, fix=fix)
        except QuestionFormatError as e:
            last = e
            continue
        if figure.points_to_missing(q["question"], q["figure"]) and not fix:
            kept, fix = q, True
            continue
        return q
    if kept is not None:
        return kept
    raise last or QuestionFormatError("문제를 만들지 못함")


def make_question(concept: dict, kind: str, material: dict, meta_pages, other_names: list, usage=None) -> dict:
    """개념 하나의 진단 문제. 객관식이 형식에 어긋나거나 읽지 못하면 같은 개념의 서술형으로 대신 낸다."""
    valid = evidence_pages(concept, meta_pages)
    ptext = pages_text(material["pages"], valid)
    others = others_text(other_names, concept["name"])
    if kind == MCQ:
        try:
            return _make_mcq(concept["name"], ptext, valid, others, usage)
        except (QuestionFormatError, llm.BadJSONError):
            pass
    return _make_essay(concept["name"], ptext, valid, others, usage)


# ---------- 답과 채점 ----------

def clean_answer(text) -> str:
    """답안을 프롬프트에 넣기 전에 공백을 정리하고 꺾쇠를 바꾼다(자르지 않는다)."""
    out = re.sub(r"\s+", " ", str(text or "")).strip()
    return out.replace("<", "‹").replace(">", "›")


def clean_confusion(text) -> str:
    """헷갈린 점: 공백 정리, 300자, 꺾쇠 바꾸기."""
    return clean_answer(str(text or ""))[:CONFUSION_MAX_CHARS].strip()


def is_answered(q: dict, answer=None, dont_know=False, choice=None) -> bool:
    """모든 문제에 답해야 채점한다. 객관식은 보기(0~3) 또는 '모르겠어요'(-1)."""
    if q["kind"] == MCQ:
        return isinstance(choice, int) and not isinstance(choice, bool) and -1 <= choice <= 3
    return bool(dont_know) or bool(str(answer or "").strip())


def status_of(score: int, error_type=None) -> str:
    """상태는 코드가 점수로 정한다. '개념 혼동'은 4~7점이어도 모름."""
    if score >= 8:
        return "앎"
    if score >= 4:
        return "모름" if error_type == "개념 혼동" else "헷갈림"
    return "모름"


def _zero(kind, reason) -> dict:
    return Grading(kind=kind, score=0, status="모름", error_type="무응답", reason=reason).model_dump()


def grade_mcq(q: dict, choice, guessed: bool = False) -> dict:
    """객관식 채점은 코드가 한다(AI 호출 없음)."""
    if choice is None or isinstance(choice, bool) or not isinstance(choice, int) or not -1 <= choice <= 3:
        return _zero(MCQ, REASON_NO_CHOICE)
    if choice == -1:
        return _zero(MCQ, REASON_DONT_KNOW)
    right = q["answer_index"]
    if choice == right:
        if guessed:
            return Grading(kind=MCQ, score=5, status="헷갈림", error_type="찍어서 맞힘",
                           reason="정답이지만 확신 없이 골라 헷갈림으로 표시했어요.").model_dump()
        return Grading(kind=MCQ, score=10, status="앎", reason="정답을 확신하고 골랐어요.").model_dump()
    return Grading(kind=MCQ, score=0, status="모름", error_type="오답",
                   reason=f"{eul(choice)} 골랐지만 정답은 {ieyo(right)}.").model_dump()


def grade_without_ai(q: dict, answer=None, dont_know=False, choice=None, guessed=False):
    """AI 없이 채점할 수 있으면 결과를, 서술형 답이 있어 AI가 필요하면 None을 돌려준다."""
    if q["kind"] == MCQ:
        return grade_mcq(q, choice, guessed)
    if dont_know:
        return _zero(ESSAY, REASON_DONT_KNOW)
    if not str(answer or "").strip():
        return _zero(ESSAY, REASON_BLANK)
    return None


def _to_int(v) -> int:
    try:
        return int(round(float(v)))  # .5는 가까운 짝수 쪽(파이썬 기본)
    except (TypeError, ValueError):
        return 0


def clean_grading(raw, q: dict, valid_pages) -> dict:
    """03-B 답 다듬기. 부분 점수·null·글자도 정수로 바꾸고 항목 배점으로 자른다."""
    if not isinstance(raw, dict):
        raise llm.BadJSONError("채점 결과가 객체가 아님")
    maxes = [r["score"] for r in q.get("rubric") or []]
    given = raw.get("rubric_scores")
    given = given if isinstance(given, list) else []
    if maxes and len(given) == len(maxes):
        scores = [max(0, min(m, _to_int(v))) for v, m in zip(given, maxes)]
        total = sum(scores)  # AI가 적은 score가 아니라 잘라 낸 항목의 합
    else:
        scores = []
        total = _to_int(raw.get("score"))
    total = max(0, min(10, total))
    error_type = raw.get("error_type")
    if error_type in (None, "", "null", "None"):
        error_type = None
    elif error_type not in ERROR_TYPES:
        error_type = "기타"
    reason = raw.get("reason")
    reason = strip_bad_cites(str(reason).strip(), valid_pages) if reason not in (None, "null") else ""
    return Grading(kind=ESSAY, score=total, status=status_of(total, error_type), error_type=error_type,
                   reason=reason, rubric_scores=scores).model_dump()


def grading_prompt(name: str, q: dict, answer: str, ptext: str) -> str:
    qjson = {"question": q["question"], "answer": q["answer"], "rubric": q["rubric"]}
    if q.get("figure"):
        qjson["figure"] = figure.to_text(q["figure"])
    return prompts.fill("03B", CONCEPT_NAME=name,
                        QUESTION_JSON=json.dumps(qjson, ensure_ascii=False, indent=1),
                        PAGES=ptext, ANSWER=clean_answer(answer))


def grade_essay(concept: dict, q: dict, answer: str, material: dict, meta_pages, usage=None) -> dict:
    """서술형 채점(호출 3-B)."""
    valid = evidence_pages(concept, meta_pages)
    text = grading_prompt(concept["name"], q, answer, pages_text(material["pages"], valid))
    raw = llm.ask_json(text, AI_MAX_TOKENS, usage=usage)
    return clean_grading(raw, q, valid)


# ---------- 샘플 체험용 예시 답 (F11) ----------

def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", str(text or "").strip())
    return parts[0] if parts and parts[0] else str(text or "").strip()


def example_answers(questions: dict) -> dict:
    """문제 순서대로 돌려 가며 답을 만든다. 앎·헷갈림·모름이 모두 나오게.

    서술형: 모범 답안 전체 → 첫 문장만 → '모르겠어요'
    객관식: (정답, 확신) → (정답, 찍음 + 헷갈린 점) → (정답 다음 보기, 확신)
    """
    out, n_essay, n_mcq = {}, 0, 0
    for cid, q in questions.items():
        given = {"answer": "", "dont_know": False, "choice": None, "guessed": False, "confusion": ""}
        if q["kind"] == MCQ:
            turn = n_mcq % 3
            n_mcq += 1
            if turn == 0:
                given["choice"] = q["answer_index"]
            elif turn == 1:
                given.update(choice=q["answer_index"], guessed=True, confusion=EXAMPLE_CONFUSION)
            else:
                given["choice"] = (q["answer_index"] + 1) % 4
        else:
            turn = n_essay % 3
            n_essay += 1
            if turn == 0:
                given["answer"] = q["answer"]
            elif turn == 1:
                given["answer"] = _first_sentence(q["answer"])
            else:
                given["dont_know"] = True
        out[cid] = given
    return out
