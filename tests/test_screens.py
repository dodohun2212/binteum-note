"""화면 쪽 기준: T-37(화면), T-42·T-47(소스), T-46, T-48, T-51, T-52, T-53, T-66.

화면 동작은 AppTest로 실제로 눌러 확인한다. 소스 글자 검사는 T-42·T-46·T-47·T-51에만 쓴다.
"""
import ast
import re
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
N_SAMPLE_CONCEPTS = 13


def press(at, part):
    """이름에 part가 든 버튼을 누른다."""
    next(b for b in at.button if part in b.label).click().run()
    return at


def press_exact(at, label):
    """이름이 정확히 label인 버튼을 누른다."""
    next(b for b in at.button if b.label == label).click().run()
    return at


def new_session():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert len(at.exception) == 0
    return at


def to_diagnosis(at):
    """샘플 체험 → 진단하기까지."""
    press(at, "샘플")
    press(at, "진단하기")
    assert len(at.exception) == 0
    return at


def to_filled(at):
    """샘플 체험 → 진단하기 → 예시 답 채우기까지."""
    to_diagnosis(at)
    press(at, "예시 답")
    assert len(at.exception) == 0
    return at


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def func_source(rel: str, name: str) -> str:
    """파일 안 함수 하나의 소스."""
    text = read(rel)
    node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)


def session_confusions(at) -> dict:
    """화면과 같은 규칙: 객관식에서 보기를 고르고 '확신 없이'를 체크했을 때만 헷갈린 점을 쓴다."""
    ss = at.session_state
    out = {}
    for cid, text in ss["confusion"].items():
        choice = ss["mcq_choice"].get(cid)
        if ss["guessed"].get(cid) and isinstance(choice, int) and choice >= 0 and str(text or "").strip():
            out[cid] = str(text).strip()
    return out


# ---------- T-37 화면: 저장된 샘플 문제를 다른 세션이 다시 쓴다 ----------

def test_second_session_reuses_saved_sample_questions():
    st.cache_resource.clear()
    a = to_diagnosis(new_session())
    assert a.session_state["step"] == 3
    n = len(a.session_state["questions"])
    assert n == 11
    assert a.session_state["usage"].calls == 11

    # 서버 공용 저장소를 지우지 않고 새 세션을 연다
    b = to_diagnosis(new_session())
    assert b.session_state["step"] == 3
    assert b.session_state["usage"].calls == 0
    assert len(b.session_state["questions"]) == n


# ---------- T-46 기다리는 안내 위치 (CSS) ----------

def test_spinner_css_fixed():
    source = read("app.py")
    assert '[data-testid="stSpinner"]' in source
    assert "position: fixed" in source
    assert re.search(r'\[data-testid="stSpinner"\]\s*\{[^}]*position:\s*fixed', source) is not None


# ---------- T-48 프롬프트만 바뀐 배포 ----------

def _times() -> dict:
    return {"modules": {"llm.py@core": 100.0, "config.py@당일": 50.0}, "prompts": {"01_개념추출.md": 10.0}}


def test_needs_reload_without_previous():
    from core.guard import needs_reload

    assert needs_reload(None, _times()) is True


def test_needs_reload_when_prompt_time_changed():
    from core.guard import needs_reload

    now = _times()
    now["prompts"]["01_개념추출.md"] = 11.0
    assert needs_reload(_times(), now) is True


def test_needs_reload_when_previous_has_no_prompts():
    from core.guard import needs_reload

    previous = {"modules": _times()["modules"]}
    assert needs_reload(previous, _times()) is True


def test_needs_reload_when_module_time_changed():
    from core.guard import needs_reload

    now = _times()
    now["modules"]["llm.py@core"] = 101.0
    assert needs_reload(_times(), now) is True


def test_needs_reload_false_when_same():
    from core.guard import needs_reload

    assert needs_reload(_times(), _times()) is False


# ---------- T-51 분석 중 안내 유지 ----------

def test_analyze_collects_notices_instead_of_drawing():
    body = func_source("screens/s01.py", "analyze")
    chunks = [body[m.end():m.end() + 200] for m in re.finditer(r"notices\.append\(", body)]
    for code in ("E-05", "E-10", "E-13"):
        assert any(code in c for c in chunks), f"{code} 안내를 notices에 담지 않아요"
    assert "st.warning(" not in body


def test_notices_are_drawn_on_s02():
    st.cache_resource.clear()
    at = new_session()
    press(at, "샘플")
    assert at.session_state["step"] == 2
    assert not any("테스트 안내 (E-10)" in w.value for w in at.warning)
    at.session_state["notices"] = ["테스트 안내 (E-10)"]
    at.run()
    assert len(at.exception) == 0
    assert any("테스트 안내 (E-10)" in w.value for w in at.warning)


# ---------- T-52 헷갈린 점을 적은 '복습만' 개념 ----------

def _review_items() -> list:
    return [{"concept_id": cid, "name": cid, "action": "복습만", "priority": 5} for cid in ("c1", "c2", "c3")]


def test_split_review_opens_concept_with_confusion():
    from core.priority import split_review

    opened, folded = split_review(_review_items(), {"c2": "②와 ③이 어떻게 다른지 모르겠어요"})
    assert [p["concept_id"] for p in opened] == ["c2"]
    assert [p["concept_id"] for p in folded] == ["c1", "c3"]


def test_split_review_folds_all_without_confusion():
    from core.priority import split_review

    opened, folded = split_review(_review_items(), {})
    assert opened == []
    assert [p["concept_id"] for p in folded] == ["c1", "c2", "c3"]


# ---------- T-53 채점 실패 원인별 문구 ----------

def test_grade_failure_shows_real_cause():
    st.cache_resource.clear()
    at = to_filled(new_session())
    assert any(b.label == "채점하기" for b in at.button)
    essay_id = next(cid for (cid, kind), q in at.session_state["questions"].items() if q["kind"] == "서술형")
    at.session_state["grade_failed"] = [essay_id]
    at.session_state["grade_error"] = ("AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요", "E-07", "APIError")
    at.run()
    assert len(at.exception) == 0
    errors = [e.value for e in at.error]
    box = next((e for e in errors if "채점하지 못했어요" in e), None)
    assert box is not None, f"채점 실패 상자가 없어요: {errors}"
    assert "서술형 1문제를 채점하지 못했어요" in box
    assert "(E-07)" in box
    assert "(E-08)" not in box
    labels = [b.label for b in at.button]
    assert "채점 못한 문제 다시 채점" in labels
    assert "채점하기" not in labels


# ---------- T-66 화면 바꾸기 전에 만들기 ----------

def test_diagnose_button_makes_all_questions_before_s03():
    st.cache_resource.clear()
    at = new_session()
    press(at, "샘플")
    label = next(b.label for b in at.button if "진단하기" in b.label)
    n = int(re.match(r"(\d+)개 개념 진단하기", label).group(1))
    press(at, "진단하기")  # 한 번만 누른다
    assert len(at.exception) == 0
    assert at.session_state["step"] == 3
    assert len(at.session_state["questions"]) == n
    assert len(at.session_state["diag_ids"]) == n


def test_study_button_makes_explanations_before_s04_and_no_notes():
    from core.priority import auto_explain_ids

    st.cache_resource.clear()
    at = to_filled(new_session())
    press_exact(at, "채점하기")
    assert len(at.session_state["grading"]) == len(at.session_state["questions"])
    calls_before = at.session_state["usage"].calls

    press_exact(at, "공부 순서 보기")  # 한 번만 누른다
    assert len(at.exception) == 0
    ss = at.session_state
    assert ss["step"] == 4
    wanted = auto_explain_ids(ss["priorities"], session_confusions(at))
    assert len(wanted) >= 1
    assert sorted(ss["explanations"]) == sorted(wanted)
    # ④ 첫 화면: 요약 노트는 아직 만들지 않았고, 늘어난 호출은 보완 설명뿐이다
    assert ss["notes_made"] is False
    assert len(ss["notes"]) == 0
    assert ss["usage"].calls - calls_before == len(ss["explanations"])


def test_notes_are_made_when_notes_view_is_chosen():
    from screens.s04 import VIEWS

    st.cache_resource.clear()
    at = to_filled(new_session())
    press_exact(at, "채점하기")
    press_exact(at, "공부 순서 보기")
    assert at.session_state["step"] == 4
    assert at.session_state["notes_made"] is False
    calls_before = at.session_state["usage"].calls

    at.button_group[0].select(VIEWS[1]).run()  # 요약 노트 보기 고르기
    assert len(at.exception) == 0
    ss = at.session_state
    assert ss["s04_view"] == VIEWS[1]
    assert ss["notes_made"] is True
    assert len(ss["concepts"]) == N_SAMPLE_CONCEPTS
    assert len(ss["notes"]) == N_SAMPLE_CONCEPTS
    by_ai = sum(1 for n in ss["notes"].values() if n["detail"] in ("자세히", "보통"))
    assert by_ai >= 1
    assert ss["usage"].calls - calls_before == by_ai
    # 노트를 만든 뒤에는 요약 노트 내려받기가 켜진다
    notes_buttons = [d for d in at.get("download_button") if "요약 노트 내려받기" in d.label]
    assert len(notes_buttons) == 2
    assert [d.disabled for d in notes_buttons] == [False, False]


# ---------- T-42 대본을 받자마자 가림 (소스) ----------

def test_transcript_is_masked_on_arrival():
    assert "stt.resolve_transcript(" in func_source("screens/s01.py", "analyze")
    assert "mask(" in func_source("core/stt.py", "resolve_transcript")


def test_resolve_transcript_masks_pasted_text():
    from core import stt

    text, source, notice = stt.resolve_transcript("질문은 kim@koreatech.ac.kr 또는 010-1234-5678로 주세요")
    assert source == "paste"
    assert notice is None
    assert "kim@koreatech.ac.kr" not in text
    assert "010-1234-5678" not in text
    assert "[마스킹]" in text


def test_no_session_memory_only_wording():
    paths = [ROOT / "app.py"] + sorted((ROOT / "screens").glob("*.py"))
    readme = ROOT / "README.md"
    if readme.exists():  # README가 아직 없으면 그 부분은 건너뛴다
        paths.append(readme)
    assert len(paths) >= 7
    for path in paths:
        assert "세션 메모리에만" not in path.read_text(encoding="utf-8"), path.name


# ---------- T-47 답 칸 안내 (소스) ----------

def test_answer_hint_says_two_to_three_sentences():
    source = read("screens/s03.py")
    assert re.search(r'ANSWER_HINT\s*=\s*"[^"\n]*2~3문장', source) is not None
    assert "2~5문장" not in source


def test_answer_box_placeholder_on_screen():
    st.cache_resource.clear()
    at = to_diagnosis(new_session())
    boxes = [t for t in at.text_area if t.label == "내 답"]
    assert len(boxes) >= 1
    for box in boxes:
        assert "2~3문장" in box.placeholder
