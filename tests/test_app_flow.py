"""T-54 화면 흐름: 샘플 체험 → 진단하기 → 답 없이 채점 → 예시 답 채우기 → 채점 → 공부 순서 → ⑤.

가짜 AI(BINTM_FAKE_AI=1)로 실제 화면을 AppTest로 눌러 확인한다.
"""
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
MISSING_MARK = "아직 답하지 않았어요"


def press(at, part):
    """이름에 part가 든 버튼을 누른다."""
    next(b for b in at.button if part in b.label).click().run()
    return at


def press_exact(at, label):
    """이름이 정확히 label인 버튼을 누른다."""
    next(b for b in at.button if b.label == label).click().run()
    return at


def page_html(at) -> str:
    """화면에 그려진 HTML 글 전부."""
    return "\n".join(h.body for h in at.html)


def test_flow_sample_to_settings():
    st.cache_resource.clear()  # 앞 테스트가 서버 공용 저장소에 넣은 문제·횟수를 지운다
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert len(at.exception) == 0
    assert at.session_state["step"] == 1

    # ① 샘플 체험 → ②
    press(at, "샘플")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 2

    # ② 진단하기 → ③
    press(at, "진단하기")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 3
    n_questions = len(at.session_state["questions"])
    assert n_questions >= 3

    # ③ 답 없이 채점: 채점하지 않고, 카드마다 미답 표시가 이 화면에서 바로 보인다
    calls_before = at.session_state["usage"].calls
    press_exact(at, "채점하기")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 3
    assert len(at.session_state["grading"]) == 0
    assert at.session_state["usage"].calls == calls_before
    marks = [h for h in at.html if MISSING_MARK in h.body]
    assert len(marks) == n_questions
    assert any("아직 답하지 않은 문제: Q1" in h.body for h in at.html)

    # ③ 예시 답 채우기 → 미답 표시가 사라진다
    press(at, "예시 답")
    assert len(at.exception) == 0
    assert not any(MISSING_MARK in h.body for h in at.html)
    assert len(at.session_state["grading"]) == 0

    # ③ 채점: 앎·헷갈림·모름이 모두 나온다
    press_exact(at, "채점하기")
    assert len(at.exception) == 0
    grading = at.session_state["grading"]
    assert len(grading) == n_questions
    statuses = [g["status"] for g in grading.values()]
    for status in ("앎", "헷갈림", "모름"):
        assert statuses.count(status) >= 1, f"채점 결과에 '{status}'이 없어요: {statuses}"
    assert len(at.error) == 0

    # ③ 공부 순서 보기 → ④
    press_exact(at, "공부 순서 보기")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 4
    groups = at.button_group
    assert len(groups) == 1
    assert len(groups[0].options) == 2  # 보기 고르기 옵션 2개
    labels = [d.label for d in at.get("download_button")]
    assert len(labels) == 4  # 위·아래 두 곳에 2종씩
    assert sum("공부 순서·오답노트 내려받기" in x for x in labels) == 2
    assert sum("요약 노트 내려받기" in x for x in labels) == 2
    assert "내가 헷갈린 점에 대한 답" in page_html(at)

    # ⑤ 안내·설정
    press(at, "⑤")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 5
    assert "AI 호출 수" in page_html(at)
