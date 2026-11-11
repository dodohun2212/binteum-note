"""T-69 첫 화면, T-70 샘플 분석은 저장된 결과로. AppTest로 실제 화면을 열어 확인한다."""
import html as html_lib
import re
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def press(at, part):
    """이름에 part가 든 버튼을 누른다."""
    next(b for b in at.button if part in b.label).click().run()
    return at


def page_html(at) -> str:
    """화면에 그려진 HTML 글 전부."""
    return "\n".join(h.body for h in at.html)


def table_value(at, label: str) -> str:
    """⑤ 표에서 label 줄의 값."""
    found = re.search(re.escape(label) + r"</th><td>([^<]*)</td>", page_html(at))
    assert found is not None, f"⑤ 표에 '{label}' 줄이 없어요"
    return found.group(1)


def open_first_screen():
    st.cache_resource.clear()  # 앞 테스트가 서버 공용 저장소에 넣은 문제·횟수를 지운다
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert len(at.exception) == 0
    return at


# ---------- T-69 첫 화면 ----------

def test_first_screen_problem_line_and_no_ai_call():
    at = open_first_screen()
    assert at.session_state["step"] == 1
    assert "코리아텍" in page_html(at)  # 해결하는 문제 한 줄
    assert at.session_state["usage"].calls == 0


def test_first_screen_sample_button_before_upload():
    at = open_first_screen()
    kinds = list(at.main)
    sample_at = next(i for i, e in enumerate(kinds)
                     if getattr(e, "type", "") == "button" and "샘플로 1분 체험" in e.label)
    upload_at = next(i for i, e in enumerate(kinds) if getattr(e, "type", "") == "file_uploader")
    assert sample_at < upload_at
    assert "샘플" in at.button[0].label


def test_first_screen_three_differences():
    at = open_first_screen()
    body = page_html(at)
    assert "ChatGPT·에브리타임과 다른 점" in body
    card = re.search(r"다른 점</h4>\s*<ul[^>]*>(.*?)</ul>", body, re.S)
    assert card is not None
    assert len(re.findall(r"<li>", card.group(1))) == 3


def test_first_screen_preview_matches_fixture_top3():
    at = open_first_screen()
    from core import sample

    expected = [(name, pct) for name, pct, _ in sample.preview_top3()]
    assert len(expected) == 3
    body = page_html(at)
    assert "결과 미리보기" in body
    shown = re.findall(r'bn-row-name">(.*?)</span>\s*<span class="bn-row-pct">(\d+)점', body, re.S)
    shown = [(html_lib.unescape(name), int(pct)) for name, pct in shown]
    assert shown == expected


def test_first_screen_real_check_and_notice():
    at = open_first_screen()
    from core.html import NOTICE

    body = html_lib.unescape(page_html(at))
    assert "실제 수업으로 확인" in body
    assert "17개 중 15개" in body
    assert NOTICE in body


# ---------- T-70 샘플 분석은 저장된 결과로 ----------

def test_sample_uses_saved_result_without_ai_call():
    at = open_first_screen()
    press(at, "샘플")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 2
    assert at.session_state["usage"].calls == 0
    assert any("미리 저장해 둔 분석 결과" in i.value for i in at.info)


def test_sample_does_not_use_daily_analysis_count():
    at = open_first_screen()
    press(at, "샘플")
    assert at.session_state["step"] == 2
    press(at, "⑤")
    assert len(at.exception) == 0
    assert at.session_state["step"] == 5
    # 저장된 결과만 쓴 분석은 하루 횟수에서 빼지 않는다
    assert table_value(at, "서버 전체 오늘 분석") == "0번"
    assert table_value(at, "이 화면에서 한 분석") == "1번"
    assert table_value(at, "AI 호출 수") == "0번"
