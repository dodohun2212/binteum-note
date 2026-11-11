"""대본 가리기, 틀린 항목만 버리기, 내가 놓친 점, 프롬프트 문구 (T-42 core 부분, T-43~T-45, T-47)."""
import pytest

from core import concepts, diagnose, explain, llm, prompts, utterances


def last_tag(text: str, tag: str) -> str:
    """프롬프트의 마지막 <tag>…</tag> 칸 글."""
    end = text.rfind(f"</{tag}>")
    start = text.rfind(f"<{tag}>", 0, end)
    return text[start + len(tag) + 2:end].strip()


# ---------- T-42 ----------

RAW_TRANSCRIPT = (
    "오늘 공지부터 하겠습니다. 학번 2021136001 학생은 010-1234-5678로 연락 주세요. "
    "과제는 kim.student@koreatech.ac.kr 주소로 보내면 됩니다. "
    "힙의 삭제 연산은 시험에 꼭 나옵니다."
)


def test_call2_prompt_has_masked_transcript_only(monkeypatch):
    seen = []

    def fake_ask(text, *args, **kwargs):
        seen.append(text)
        return {"utterances": [
            {"concept_id": "c1", "quote": "학번 [마스킹] 학생은 [마스킹]로 연락 주세요.",
             "type": "emphasis", "strength": 1},
            {"concept_id": "c1", "quote": "힙의 삭제 연산은 시험에 꼭 나옵니다.", "type": "exam_hint", "strength": 3},
            {"concept_id": "c1", "quote": "학번 2021136001 학생은 010-1234-5678로 연락 주세요.",
             "type": "emphasis", "strength": 1},
        ]}

    monkeypatch.setattr(llm, "ask_json", fake_ask)
    cs = [{"id": "c1", "name": "힙의 삭제 연산", "summary": "루트를 꺼낸다", "keywords": ["삭제"]}]
    found = utterances.find_utterances(RAW_TRANSCRIPT, cs)

    assert len(seen) == 1
    prompt = seen[0]
    assert "2021136001" not in prompt
    assert "010-1234-5678" not in prompt
    assert "kim.student@koreatech.ac.kr" not in prompt
    sent = last_tag(prompt, "transcript")
    assert sent.count("[마스킹]") == 3
    assert "힙의 삭제 연산은 시험에 꼭 나옵니다." in sent

    # 가린 대본의 문장을 인용한 발화는 인용 검사를 통과하고, 원문 번호가 든 인용은 버려진다
    quotes = [u["quote"] for u in found]
    assert quotes == ["학번 [마스킹] 학생은 [마스킹]로 연락 주세요.", "힙의 삭제 연산은 시험에 꼭 나옵니다."]
    assert all(u["concept_id"] == "c1" for u in found)


def test_no_transcript_makes_no_call(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "ask_json", lambda text, *a, **k: seen.append(text) or {})
    assert utterances.find_utterances("   ", [{"id": "c1", "name": "힙"}]) == []
    assert seen == []


# ---------- T-43 ----------

def test_clean_concepts_drops_only_bad_items():
    raw = {"concepts": [
        {"id": "c1", "name": "트리의 기본 용어", "summary": "용어", "pages": "3-4"},
        {"id": None, "name": "힙의 정의", "summary": "힙", "pages": "p.5"},
        {"id": "c3", "name": "", "pages": [1]},        # 이름 없음
        "x",                                           # 글자 하나뿐인 항목
        {"id": "c5", "name": "이진 트리의 순회", "pages": [2, 99]},
    ]}
    out = concepts.clean_concepts(raw, 10)
    got = out["concepts"]
    assert [c["name"] for c in got] == ["트리의 기본 용어", "힙의 정의", "이진 트리의 순회"]
    assert [c["id"] for c in got] == ["c1", "c2", "c5"]
    assert got[0]["pages"] == [3, 4]
    assert got[1]["pages"] == [5]
    assert got[2]["pages"] == [2]


@pytest.mark.parametrize("raw", [
    {"concepts": [{"id": "c1", "name": ""}, "x", None]},
    {"concepts": []},
    {"concepts": "없음"},
    {},
    "JSON이 아님",
])
def test_clean_concepts_nothing_usable_raises_e09(raw):
    with pytest.raises(concepts.NoConceptsError) as err:
        concepts.clean_concepts(raw, 10)
    assert err.value.code == "E-09"


def test_clean_utterances_drops_bad_items_and_fixes_numeric_id():
    transcript = "힙 삭제는 시험에 꼭 나옵니다. 순회는 정말 중요합니다."
    cs = [{"id": "c5", "name": "이진 트리의 순회"}, {"id": "c11", "name": "힙의 삭제 연산"}]
    raw = {"utterances": [
        "x",
        None,
        {"concept_id": 5, "quote": "순회는 정말 중요합니다.", "type": "모르는 종류", "strength": 2},
        {"concept_id": 5, "quote": "순회는 정말 중요합니다.", "type": "emphasis", "strength": 2},
        {"concept_id": "c11", "quote": "대본에 없는 말입니다.", "type": "emphasis", "strength": 2},
    ]}
    out = utterances.clean_utterances(raw, transcript, cs)
    assert len(out) == 1
    assert out[0]["concept_id"] == "c5"
    assert out[0]["concept_name"] == "이진 트리의 순회"
    assert out[0]["type"] == "emphasis"
    assert out[0]["quote"] == "순회는 정말 중요합니다."


# ---------- T-44 ----------

NOT_CHECKED = "아직 확인하지 않은 개념이다."


def essay_q():
    return diagnose.clean_essay({"question": "삭제 과정을 쓰시오.", "answer": "루트를 꺼내고 내린다.",
                                 "rubric": [{"point": "과정", "score": 10}]}, [1])


def mcq_q():
    return diagnose.clean_mcq({"question": "옳은 것은?", "choices": ["가", "나", "다", "라"],
                               "answer_index": 0}, [1])


@pytest.mark.parametrize("gap", [NOT_CHECKED, "", None])
def test_fix_gap_no_answer(gap):
    for g in (diagnose.grade_without_ai(essay_q(), answer="", dont_know=True),   # 모르겠어요
              diagnose.grade_without_ai(essay_q(), answer="  "),                 # 빈 답
              diagnose.grade_without_ai(mcq_q(), choice=-1)):
        assert g["error_type"] == "무응답"
        out = explain.fix_gap(gap, g)
        assert "아직 확인하지 않은" not in out
        assert "답하지 못했다" in out


@pytest.mark.parametrize("gap", [NOT_CHECKED, "", None])
def test_fix_gap_wrong_answer(gap):
    q = mcq_q()
    wrong = diagnose.grade_mcq(q, (q["answer_index"] + 1) % 4)
    essay_wrong = {"kind": "서술형", "score": 2, "status": "모름", "error_type": "개념 혼동", "reason": "혼동"}
    for g in (wrong, essay_wrong):
        out = explain.fix_gap(gap, g)
        assert "아직 확인하지 않은" not in out
        assert "틀리" in out
        assert "답하지 못했다" not in out


def test_fix_gap_not_diagnosed_stays():
    assert explain.fix_gap(NOT_CHECKED, None) == NOT_CHECKED


def test_fix_gap_keeps_specific_sentence():
    specific = "삭제를 삽입과 혼동했다."
    q = mcq_q()
    for g in (None, diagnose.grade_without_ai(essay_q(), dont_know=True),
              diagnose.grade_mcq(q, (q["answer_index"] + 1) % 4)):
        assert explain.fix_gap(specific, g) == specific


def test_clean_explanation_applies_fix_gap():
    raw = {"my_gap": NOT_CHECKED, "explanation": "설명 문장이다."}
    g = diagnose.grade_without_ai(essay_q(), dont_know=True)
    fixed = explain.clean_explanation(raw, "c1", [1], "", g)
    assert "아직 확인하지 않은" not in fixed["my_gap"]
    assert "답하지 못했다" in fixed["my_gap"]
    assert explain.clean_explanation(raw, "c1", [1], "", None)["my_gap"] == NOT_CHECKED


# ---------- T-45, T-47 ----------

@pytest.mark.parametrize("key", ["03B", "04"])
def test_prompt_says_not_to_blame_material(key):
    assert "강의자료에 오기나 오류가 있다고 쓰지 않습니다" in prompts.load(key)


def test_prompt_03a_question_size():
    text = prompts.load("03A")
    assert "최대 2가지" in text
    assert "2~3문장" in text
    assert "2~4개 요소" in text
    assert "2~5" not in text
