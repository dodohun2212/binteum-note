"""T-01~T-07, T-14, T-15: 출제 점수, 우선순위, 상태 판정, 인용·쪽 번호 검사."""
import pytest

from core import cites, diagnose, priority, score, utterances


def _concept(cid="c1", name="개념", pages=None, **more):
    c = {"id": cid, "name": name, "pages": pages or []}
    c.update(more)
    return c


def _utt(cid="c1", kind="emphasis", quote="이건 중요합니다", strength=3):
    return {"concept_id": cid, "type": kind, "quote": quote, "strength": strength}


def _signal(row, kind):
    return sum(r["points"] for r in row["reasons"] if r["kind"] == kind)


# ---------- T-01 저장된 결과로 점수 계산 ----------

def test_t01_top3_and_last(analysis):
    rows = analysis["scores"]["scores"]
    assert {r["name"] for r in rows[:3]} == {"이진 트리의 순회", "힙의 삭제 연산", "힙의 삽입 연산"}
    assert rows[-1]["name"] == "이진 탐색 트리의 삭제"
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_t01_raw_and_pct(analysis):
    by_name = {r["name"]: r for r in analysis["scores"]["scores"]}
    expected = {"이진 트리의 순회": (13.0, 100), "힙의 삭제 연산": (12.7, 98), "힙의 삽입 연산": (12.5, 96)}
    for name, (raw, pct) in expected.items():
        assert by_name[name]["raw"] == pytest.approx(raw, abs=1e-6), name
        assert by_name[name]["pct"] == pct, name
    assert analysis["scores"]["max_raw"] == pytest.approx(13.0, abs=1e-6)


def test_t01_same_input_same_result(analysis):
    a = score.compute_scores(analysis["concepts"], analysis["utterances"], analysis["meta_pages"])
    b = score.compute_scores(analysis["concepts"], analysis["utterances"], analysis["meta_pages"])
    assert a == b
    assert a == analysis["scores"]


# ---------- T-02 음수 자르기 ----------

def test_t02_only_deferrals_gives_zero_pct():
    concepts = [_concept("c1", "미룬 개념"), _concept("c2", "보통 개념", pages=[5, 6])]
    utts = [_utt("c1", "deferral", f"이건 다음 시간에 {i}") for i in range(3)]
    rows = {r["concept_id"]: r for r in score.compute_scores(concepts, utts, [])["scores"]}
    assert rows["c1"]["raw"] <= 0
    assert rows["c1"]["raw"] == pytest.approx(3 * score.WEIGHTS["deferral"])
    assert rows["c1"]["pct"] == 0
    assert rows["c2"]["pct"] == 100


# ---------- T-03 메타 페이지 빼기 ----------

def test_t03_meta_pages_not_counted():
    out = score.compute_scores([_concept(pages=[2, 3, 15, 20])], [], [2, 3, 20])
    row = out["scores"][0]
    assert row["body_pages"] == [15]
    assert len(row["body_pages"]) == 1
    assert _signal(row, "page") == pytest.approx(1 * score.WEIGHTS["page"])


# ---------- T-04 같은 발화 두 번 ----------

def test_t04_same_quote_twice_doubles_signal():
    concepts = [_concept(pages=[5])]
    one = score.compute_scores(concepts, [_utt()], [])["scores"][0]
    two = score.compute_scores(concepts, [_utt(), _utt()], [])["scores"][0]
    assert _signal(one, "emphasis") == pytest.approx(1.0)
    assert _signal(two, "emphasis") == pytest.approx(2 * _signal(one, "emphasis"))
    assert two["raw"] - one["raw"] == pytest.approx(_signal(one, "emphasis"))


# ---------- T-05 모르는 유형 ----------

def test_t05_unknown_type_is_ignored():
    concepts = [_concept(pages=[5])]
    base = score.compute_scores(concepts, [], [])["scores"][0]
    row = score.compute_scores(concepts, [_utt(kind="foo")], [])["scores"][0]
    assert row["raw"] == base["raw"]
    assert [r["kind"] for r in row["reasons"]] == [r["kind"] for r in base["reasons"]]
    assert all(r["kind"] != "foo" for r in row["reasons"])


# ---------- T-06 이해도·우선순위 ----------

def test_t06_priorities_example():
    scores = [
        {"concept_id": "a", "name": "모르는 개념", "pct": 97},
        {"concept_id": "b", "name": "헷갈린 개념", "pct": 100},
        {"concept_id": "c", "name": "아는 개념", "pct": 96},
        {"concept_id": "d", "name": "진단 안 한 개념", "pct": 50},
    ]
    grading = {"a": {"status": "모름"}, "b": {"status": "헷갈림"}, "c": {"status": "앎"}}
    rows = priority.compute_priorities(scores, grading)
    by_id = {r["concept_id"]: r for r in rows}
    assert [by_id[k]["priority"] for k in "abcd"] == [97, 50, 0, 25]
    assert [by_id[k]["action"] for k in "abcd"] == ["지금 당장", "지금 당장", "복습만", "다음"]
    assert by_id["d"]["status"] == "진단 안 함"
    # 우선순위 높은 순으로 정렬
    assert [r["concept_id"] for r in rows] == ["a", "b", "d", "c"]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4]


# ---------- T-07 상태 판정 ----------

@pytest.mark.parametrize("points, expected", [(8, "앎"), (7, "헷갈림"), (4, "헷갈림"), (3, "모름"), (0, "모름")])
def test_t07_status_by_score(points, expected):
    assert diagnose.status_of(points) == expected


def test_t07_concept_confusion_is_unknown():
    assert diagnose.status_of(6, "개념 혼동") == "모름"
    assert diagnose.status_of(6, "계산 실수") == "헷갈림"


# ---------- T-14 인용 검사 ----------

def test_t14_quote_not_in_transcript_is_dropped():
    transcript = "오늘은 힙을 봅니다. 삽입은 시험에 꼭 나옵니다."
    concepts = [{"id": "c1", "name": "힙의 삽입 연산"}]
    raw = {"utterances": [
        {"concept_id": "c1", "quote": "삽입은 시험에 꼭 나옵니다.", "type": "exam_hint", "strength": 3},
        {"concept_id": "c1", "quote": "삭제는 기말에 반드시 출제합니다.", "type": "exam_hint", "strength": 3},
    ]}
    out = utterances.clean_utterances(raw, transcript, concepts)
    assert [u["quote"] for u in out] == ["삽입은 시험에 꼭 나옵니다."]
    assert out[0]["concept_id"] == "c1"


# ---------- T-15 쪽 번호 범위 ----------

def test_t15_keep_pages_in_range():
    assert cites.keep_pages([3, 99], range(1, 21)) == [3]
