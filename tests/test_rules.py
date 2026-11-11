"""T-55, T-57, T-58, T-61, T-62, T-63, T-68: 작은 규칙들."""
from datetime import date, datetime, timezone

import pytest

from core import cites, diagnose, export, html, score, utterances

NOW = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)  # 한국 시간 11-11 05:00


# ---------- T-55 메타 페이지 첫 줄 ----------

def test_t55_summary_sentence_is_not_meta():
    assert score.is_meta_text("8.1 트리 요약하면 다음과 같다\n트리는 계층 구조다") is False


def test_t55_first_line_summary_is_meta():
    assert score.is_meta_text("요약\n트리는 계층 구조다") is True


def test_t55_first_line_exercise_is_meta():
    assert score.is_meta_text("8.6 연습문제\n1. 순회 결과를 쓰시오") is True


def test_t55_sample_page_2_is_meta(material):
    assert score.is_meta_text(material["pages"][1]["text"]) is True


def test_t55_number_lines_are_not_meta():
    text = "측정값 표\n3.14 2.71\n1.41 1.73\n2.23 2.64\n3.16 3.31"
    assert score.is_meta_text(text) is False
    assert score.is_meta_text("3.14 2.71\n1.41 1.73\n2.23 2.64\n3.16 3.31") is False


def test_t55_find_meta_pages_on_sample(material):
    found = score.find_meta_pages(material["pages"], {"objectives_page": 3, "exercise_page": 19})
    assert found == [1, 2, 3, 19, 20]


# ---------- T-57 본문 인용 칩 ----------

def test_t57_strip_only_bad_cites():
    out = cites.strip_bad_cites("가 (p.3) 나 (p.5)", {5, 6})
    assert "(p.3)" not in out
    assert "p.3" not in out
    assert "(p.5)" in out
    assert out.startswith("가")
    assert "나" in out


def test_t57_good_cites_untouched():
    text = "가 (p.5) 나 (p.6)"
    assert cites.strip_bad_cites(text, {5, 6}) == text


# ---------- T-58 한국 날짜 ----------

def test_t58_kst_today():
    assert html.kst_today(NOW) == date(2026, 11, 11)


def test_t58_file_names_use_kst_date():
    names = export.file_names(NOW)
    assert len(names) == 2
    assert names[0] != names[1]
    for name in names:
        assert "2026-11-11" in name
        assert "2026-11-10" not in name
        assert name.endswith(".html")


def test_t58_study_html_head_uses_kst_date():
    doc = export.study_html({}, NOW)
    assert "2026-11-11" in doc
    assert "2026-11-10" not in doc


# ---------- T-61 빠른 진단 기본값 ----------

def test_t61_quick_default():
    assert diagnose.quick_default(False, 9) is True
    assert diagnose.quick_default(False, 8) is False
    assert diagnose.quick_default(True, 10) is False


# ---------- T-62 강조 발화 중복 ----------

CONCEPTS = [{"id": "c1", "name": "힙의 삽입 연산"}]


def _same(quote, n):
    return {"utterances": [{"concept_id": "c1", "quote": quote, "type": "emphasis", "strength": 3}
                           for _ in range(n)]}


def test_t62_once_in_transcript_ten_times_keeps_one():
    transcript = "오늘은 힙을 봅니다. 삽입은 정말 중요합니다. 다음으로 넘어갑시다."
    out = utterances.clean_utterances(_same("삽입은 정말 중요합니다.", 10), transcript, CONCEPTS)
    assert len(out) == 1
    assert out[0]["concept_id"] == "c1"
    assert out[0]["quote"] == "삽입은 정말 중요합니다."


def test_t62_twice_in_transcript_three_times_keeps_two():
    transcript = "삽입은 정말 중요합니다. 예제를 봅시다. 다시 말하지만 삽입은 정말 중요합니다."
    out = utterances.clean_utterances(_same("삽입은 정말 중요합니다.", 3), transcript, CONCEPTS)
    assert len(out) == 2
    assert {u["concept_id"] for u in out} == {"c1"}


# ---------- T-63 연습문제 지목 연결 ----------

def test_t63_exercise_hint_goes_to_each_concept():
    transcript = "자 그리고 연습문제 1번 3번은 꼭 풀어 오세요. 수고했습니다."
    concepts = [
        {"id": "A", "name": "개념 A", "exercise_numbers": [1]},
        {"id": "B", "name": "개념 B", "exercise_numbers": [3]},
        {"id": "C", "name": "개념 C", "exercise_numbers": [2]},
    ]
    raw = {"utterances": [{"concept_id": None, "quote": "연습문제 1번 3번은 꼭 풀어 오세요",
                           "type": "exercise_hint", "strength": 3}]}
    out = utterances.clean_utterances(raw, transcript, concepts)
    assert sorted(u["concept_id"] for u in out) == ["A", "B"]
    assert [u["type"] for u in out] == ["exercise_hint", "exercise_hint"]
    by_id = {u["concept_id"]: u for u in out}
    assert by_id["A"]["concept_name"] == "개념 A"
    assert by_id["B"]["concept_name"] == "개념 B"


# ---------- T-68 보기 조사 ----------

def test_t68_eul():
    assert [html.eul(i) for i in range(4)] == ["①을", "②를", "③을", "④를"]


def test_t68_ieyo():
    assert [html.ieyo(i) for i in range(4)] == ["①이에요", "②예요", "③이에요", "④예요"]
