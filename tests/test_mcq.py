"""객관식 문제·채점·진단 대상·예시 답 (T-18~T-24, T-40, T-65)."""
import pytest

from core import diagnose, fake_ai, llm, prompts
from core.diagnose import QuestionFormatError


def last_tag(text: str, tag: str) -> str:
    """프롬프트의 마지막 <tag>…</tag> 칸 글."""
    end = text.rfind(f"</{tag}>")
    start = text.rfind(f"<{tag}>", 0, end)
    return text[start + len(tag) + 2:end].strip()


def mcq_raw(question="힙에 대한 설명으로 옳은 것은?", choices=None, answer_index=0):
    return {"question": question,
            "choices": choices if choices is not None else ["가", "나", "다", "라"],
            "answer_index": answer_index, "explanation": "해설이다.", "source_pages": [1], "figure": None}


def essay_raw(question="과정을 쓰시오.", answer="첫 문장이다. 둘째 문장이다."):
    return {"question": question, "answer": answer,
            "rubric": [{"point": "과정", "score": 6}, {"point": "이유", "score": 4}],
            "source_pages": [1], "figure": None}


def concept_of(analysis, cid):
    return next(c for c in analysis["concepts"] if c["id"] == cid)


# ---------- T-18 ----------

@pytest.mark.parametrize("raw", [
    mcq_raw(choices=["가", "나", "다"]),              # 보기 3개
    mcq_raw(choices=["가", "나", "가", "라"]),        # 중복 보기
    mcq_raw(answer_index=4),                          # 정답 위치 4
    mcq_raw(question=""),                             # 빈 문제
    mcq_raw(question="   "),
])
def test_clean_mcq_rejects_bad_format(raw):
    with pytest.raises(QuestionFormatError):
        diagnose.clean_mcq(raw, [1])


def test_clean_mcq_strips_choice_numbering():
    q = diagnose.clean_mcq(mcq_raw(choices=["① 가", "2. 나", "C) 다", "(4) 라"], answer_index=2), [1])
    assert sorted(q["choices"]) == ["가", "나", "다", "라"]
    assert q["answer"] == "다"
    assert q["choices"][q["answer_index"]] == "다"


def test_clean_mcq_duplicate_after_numbering_removed():
    # 번호를 지우면 같은 글이 되는 보기도 중복이다
    with pytest.raises(QuestionFormatError):
        diagnose.clean_mcq(mcq_raw(choices=["① 가", "② 가", "③ 다", "④ 라"]), [1])


# ---------- T-19 ----------

def test_clean_mcq_same_question_same_order():
    raw = mcq_raw(choices=["정답 글", "오답 하나", "오답 둘", "오답 셋"], answer_index=0)
    a = diagnose.clean_mcq(raw, [1])
    b = diagnose.clean_mcq(raw, [1])
    assert a["choices"] == b["choices"]
    assert a["answer_index"] == b["answer_index"]
    assert a["answer"] == "정답 글"
    assert a["choices"][a["answer_index"]] == "정답 글"


def test_clean_mcq_answer_position_spreads():
    positions = set()
    for i in range(40):
        raw = mcq_raw(question=f"{i}번째 개념에 대한 설명으로 옳은 것은?",
                      choices=["정답 글", "오답 하나", "오답 둘", "오답 셋"], answer_index=0)
        q = diagnose.clean_mcq(raw, [1])
        assert q["choices"][q["answer_index"]] == q["answer"] == "정답 글"
        positions.add(q["answer_index"])
    assert len(positions) >= 3


# ---------- T-20 ----------

def test_grade_mcq_four_cases():
    q = diagnose.clean_mcq(mcq_raw(), [1])
    right = q["answer_index"]
    wrong = (right + 1) % 4

    g = diagnose.grade_mcq(q, right)
    assert (g["status"], g["score"], g["error_type"]) == ("앎", 10, None)

    g = diagnose.grade_mcq(q, right, guessed=True)
    assert (g["status"], g["score"], g["error_type"]) == ("헷갈림", 5, "찍어서 맞힘")

    g = diagnose.grade_mcq(q, wrong)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "오답")

    g = diagnose.grade_mcq(q, None)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "무응답")


def test_grade_mcq_wrong_guess_is_still_wrong():
    q = diagnose.clean_mcq(mcq_raw(), [1])
    g = diagnose.grade_mcq(q, (q["answer_index"] + 2) % 4, guessed=True)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "오답")


# ---------- T-21 ----------

def test_diag_targets_only_20_or_more():
    scores = [{"concept_id": f"c{i}", "pct": pct} for i, pct in enumerate([100, 40, 20, 19, 0], 1)]
    assert diagnose.diag_targets(scores) == ["c1", "c2", "c3"]
    assert diagnose.diag_targets(scores, top=2) == ["c1", "c2"]


def test_question_kind_by_mode():
    assert diagnose.question_kind(50, "섞어서") == "서술형"
    assert diagnose.question_kind(49, "섞어서") == "객관식"
    for pct in (0, 49, 50, 100):
        assert diagnose.question_kind(pct, "모두 객관식") == "객관식"
        assert diagnose.question_kind(pct, "모두 서술형") == "서술형"


# ---------- T-22, T-65 ----------

def test_mcq_with_one_choice_falls_back_to_essay(monkeypatch, analysis, material):
    calls = []

    def fake_ask(text, *args, **kwargs):
        calls.append(text[:60])
        if "프롬프트 03-C" in text[:60]:
            return {"question": "옳은 것은?", "choices": ["하나뿐"], "answer_index": 0}
        return fake_ai.answer(text)

    monkeypatch.setattr(llm, "ask_json", fake_ask)
    concept = concept_of(analysis, "c1")
    names = [c["name"] for c in analysis["concepts"]]
    q = diagnose.make_question(concept, "객관식", material, analysis["meta_pages"], names)
    assert q["kind"] == "서술형"
    assert concept["name"] in q["question"]
    assert len(q["rubric"]) >= 1
    assert q["choices"] == []
    assert any("프롬프트 03-C" in h for h in calls)
    assert "프롬프트 03-A" in calls[-1]


def test_mcq_bad_json_falls_back_to_essay(monkeypatch, analysis, material):
    def fake_ask(text, *args, **kwargs):
        if "프롬프트 03-C" in text[:60]:
            raise llm.BadJSONError("읽지 못함")
        return fake_ai.answer(text)

    monkeypatch.setattr(llm, "ask_json", fake_ask)
    concept = concept_of(analysis, "c3")
    names = [c["name"] for c in analysis["concepts"]]
    q = diagnose.make_question(concept, "객관식", material, analysis["meta_pages"], names)
    assert q["kind"] == "서술형"
    assert concept["name"] in q["question"]
    assert sum(r["score"] for r in q["rubric"]) == 10


def test_mcq_normal_stays_mcq(analysis, material):
    concept = concept_of(analysis, "c1")
    names = [c["name"] for c in analysis["concepts"]]
    q = diagnose.make_question(concept, "객관식", material, analysis["meta_pages"], names)
    assert q["kind"] == "객관식"
    assert len(q["choices"]) == 4
    assert q["choices"][q["answer_index"]] == q["answer"]


# ---------- T-23 ----------

def test_others_text_excludes_own_name():
    text = diagnose.others_text(["A", "B", "C"], "A")
    lines = text.splitlines()
    assert "- B" in lines
    assert "- C" in lines
    assert "- A" not in lines
    assert diagnose.others_text(["A"], "A") == "(없음)"
    assert diagnose.others_text([], "A") == "(없음)"


@pytest.mark.parametrize("key", ["03A", "03C"])
def test_others_text_goes_into_last_other_concepts_slot(key):
    others = diagnose.others_text(["A", "B", "C"], "A")
    text = prompts.fill(key, CONCEPT_NAME="A", OTHER_CONCEPTS=others, PAGES="=== 페이지 1 ===\n쪽 글")
    assert last_tag(text, "other_concepts") == "- B\n- C"
    empty = prompts.fill(key, CONCEPT_NAME="A", OTHER_CONCEPTS=diagnose.others_text(["A"], "A"), PAGES="쪽 글")
    assert last_tag(empty, "other_concepts") == "(없음)"


# ---------- T-24 ----------

def test_grade_without_ai_no_answer_cases():
    essay = diagnose.clean_essay(essay_raw(), [1])
    mcq = diagnose.clean_mcq(mcq_raw(), [1])
    cases = [
        (diagnose.grade_without_ai(essay, answer="   "), "비워 두어"),
        (diagnose.grade_without_ai(essay, answer="", dont_know=True), "'모르겠어요'를 골라"),
        (diagnose.grade_without_ai(mcq, choice=-1), "'모르겠어요'를 골라"),
        (diagnose.grade_without_ai(mcq, choice=None), "고르지 않아"),
    ]
    for g, phrase in cases:
        assert g is not None
        assert g["score"] == 0
        assert g["status"] == "모름"
        assert g["error_type"] == "무응답"
        assert phrase in g["reason"]


def test_grade_without_ai_essay_with_answer_needs_ai():
    essay = diagnose.clean_essay(essay_raw(), [1])
    assert diagnose.grade_without_ai(essay, answer="내가 쓴 답") is None


# ---------- T-40 ----------

def test_example_answers_rotate_and_all_answered():
    questions = {}
    for i in range(3):
        questions[f"e{i}"] = diagnose.clean_essay(essay_raw(question=f"{i}번 과정을 쓰시오."), [1])
        questions[f"m{i}"] = diagnose.clean_mcq(mcq_raw(question=f"{i}번 개념으로 옳은 것은?"), [1])
    given = diagnose.example_answers(questions)
    assert list(given) == list(questions)

    # 서술형: 모범 답안 전체 → 첫 문장만 → 모르겠어요
    assert given["e0"]["answer"] == questions["e0"]["answer"]
    assert given["e0"]["dont_know"] is False
    assert given["e1"]["answer"] == "첫 문장이다."
    assert given["e1"]["dont_know"] is False
    assert given["e2"]["dont_know"] is True

    # 객관식: (정답, 확신) → (정답, 찍음 + 헷갈린 점) → (오답)
    assert given["m0"]["choice"] == questions["m0"]["answer_index"]
    assert given["m0"]["guessed"] is False
    assert given["m1"]["choice"] == questions["m1"]["answer_index"]
    assert given["m1"]["guessed"] is True
    assert given["m1"]["confusion"] == diagnose.EXAMPLE_CONFUSION
    assert given["m2"]["choice"] in (0, 1, 2, 3)
    assert given["m2"]["choice"] != questions["m2"]["answer_index"]
    assert not given["m0"]["confusion"]
    assert not given["m2"]["confusion"]

    statuses = [diagnose.grade_mcq(questions[k], given[k]["choice"], given[k]["guessed"])["status"]
                for k in ("m0", "m1", "m2")]
    assert statuses == ["앎", "헷갈림", "모름"]

    for cid, q in questions.items():
        a = given[cid]
        assert diagnose.is_answered(q, a["answer"], a["dont_know"], a["choice"]) is True
