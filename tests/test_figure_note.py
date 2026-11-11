"""문제 그림, 그림을 가리키는 문제, 페이지 그림, 요약 노트, 내보내기 나누기 (T-25~T-30)."""
import json

import pytest

from core import diagnose, export, fake_ai, figure, llm, note, pageimg, priority
from core.html import esc


def concept_of(analysis, cid):
    return next(c for c in analysis["concepts"] if c["id"] == cid)


# ---------- T-25 ----------

def test_clean_figure_accepts_valid():
    tree = figure.clean_figure({"kind": "tree", "nodes": ["A", "B", "C", None, "D"], "caption": "예시"})
    assert tree == {"kind": "tree", "nodes": ["A", "B", "C", None, "D"], "caption": "예시"}
    arr = figure.clean_figure({"kind": "array", "items": [90, 75, 80], "start": 1})
    assert arr["kind"] == "array"
    assert arr["items"] == ["90", "75", "80"]
    assert arr["start"] == 1
    table = figure.clean_figure({"kind": "table", "header": ["연산", "시간"], "rows": [["삽입", "O(log n)"]]})
    assert table["kind"] == "table"
    assert table["header"] == ["연산", "시간"]
    assert table["rows"] == [["삽입", "O(log n)"]]


@pytest.mark.parametrize("raw", [
    {"kind": "tree", "nodes": [None, "A", "B"]},                          # 루트 없음
    {"kind": "tree", "nodes": ["A", None, "C", "D"]},                     # 부모 없는 노드
    {"kind": "tree", "nodes": [str(i) for i in range(32)]},               # 31칸 초과
    {"kind": "array", "items": [str(i) for i in range(32)]},              # 31칸 초과
    {"kind": "array", "items": []},                                       # 빈 배열
    {"kind": "table", "header": ["a", "b"], "rows": [["1", "2"], ["3"]]},  # 열 수가 다른 표
    {"kind": "graph", "nodes": ["A"]},                                    # 모르는 kind
    {"nodes": ["A"]},
    "tree",
    None,
])
def test_clean_figure_rejects_bad(raw):
    assert figure.clean_figure(raw) is None


def test_clean_figure_31_nodes_is_ok():
    fig = figure.clean_figure({"kind": "tree", "nodes": [str(i) for i in range(31)]})
    assert fig is not None
    assert len(fig["nodes"]) == 31


# ---------- T-26 ----------

def test_tree_svg_counts_and_data_uri():
    fig = figure.clean_figure({"kind": "tree", "nodes": ["A", "B", "C", "D"]})
    svg = figure.tree_svg(fig)
    assert svg.count("<circle") == 4
    assert svg.count("<line") == 3
    html = figure.to_html(fig)
    assert "data:image/svg+xml;base64," in html
    assert "<svg" not in html


def test_array_html_index_starts_at_one():
    fig = figure.clean_figure({"kind": "array", "items": ["90", "75", "80"], "start": 1})
    html = figure.to_html(fig)
    assert '<tr class="bn-idx"><td>1</td><td>2</td><td>3</td></tr>' in html
    fig0 = figure.clean_figure({"kind": "array", "items": ["90", "75", "80"]})
    assert '<tr class="bn-idx"><td>0</td><td>1</td><td>2</td></tr>' in figure.to_html(fig0)


def test_array_and_table_text_is_escaped():
    arr = figure.to_html(figure.clean_figure({"kind": "array", "items": ["<b>9</b>", "7"], "start": 0}))
    assert "&lt;b&gt;" in arr
    assert "<b>" not in arr
    table = figure.to_html(figure.clean_figure(
        {"kind": "table", "header": ["<b>열</b>", "값"], "rows": [["<b>x</b>", "1"]], "caption": "<b>표</b>"}))
    assert table.count("&lt;b&gt;") == 3
    assert "<b>" not in table


# ---------- T-27 ----------

def test_points_to_missing_rules():
    assert figure.points_to_missing("p.9 그림의 트리에서 전위 순회 결과를 쓰시오.", None) is True
    fig = {"kind": "tree", "nodes": ["A", "B"], "caption": ""}
    assert figure.points_to_missing("p.9 그림의 트리에서 전위 순회 결과를 쓰시오.", fig) is True  # 쪽 번호
    assert figure.points_to_missing("아래 트리에서 전위 순회 결과를 쓰시오.", None) is True
    assert figure.points_to_missing("아래 트리에서 전위 순회 결과를 쓰시오.", fig) is False
    assert figure.points_to_missing("전위 순회의 방문 순서를 쓰시오.", None) is False


def test_essay_pointing_to_figure_is_remade(monkeypatch, analysis, material):
    seen = []
    rubric = [{"point": "순서", "score": 6}, {"point": "이유", "score": 4}]

    def fake_ask(text, *args, **kwargs):
        seen.append(text)
        if len(seen) == 1:
            return {"question": "p.9 그림의 트리에서 전위 순회 순서를 쓰시오.", "answer": "A, B, C 순서다.",
                    "rubric": rubric, "source_pages": [9], "figure": None}
        return {"question": "아래 트리에서 전위 순회 순서를 쓰시오.", "answer": "A, B, D, C 순서다.",
                "rubric": rubric, "source_pages": [9],
                "figure": {"kind": "tree", "nodes": ["A", "B", "C", "D"], "caption": "예시 트리"}}

    monkeypatch.setattr(llm, "ask_json", fake_ask)
    concept = concept_of(analysis, "c5")
    names = [c["name"] for c in analysis["concepts"]]
    q = diagnose.make_question(concept, "서술형", material, analysis["meta_pages"], names)
    assert len(seen) == 2
    assert "## 다시 만들기" not in seen[0]
    assert "## 다시 만들기" in seen[1]
    assert q["kind"] == "서술형"
    assert q["question"] == "아래 트리에서 전위 순회 순서를 쓰시오."
    assert q["figure"]["kind"] == "tree"
    assert q["figure"]["nodes"] == ["A", "B", "C", "D"]


def test_mcq_pointing_to_figure_twice_becomes_essay(monkeypatch, analysis, material):
    mcq_prompts = []

    def fake_ask(text, *args, **kwargs):
        if "프롬프트 03-C" in text[:60]:
            mcq_prompts.append(text)
            return {"question": "p.9 그림의 트리에서 옳은 것은?", "choices": ["가", "나", "다", "라"],
                    "answer_index": 1, "explanation": "해설이다.", "source_pages": [9], "figure": None}
        return fake_ai.answer(text)

    monkeypatch.setattr(llm, "ask_json", fake_ask)
    concept = concept_of(analysis, "c5")
    names = [c["name"] for c in analysis["concepts"]]
    q = diagnose.make_question(concept, "객관식", material, analysis["meta_pages"], names)
    assert len(mcq_prompts) == 2
    assert "## 다시 만들기" not in mcq_prompts[0]
    assert "## 다시 만들기" in mcq_prompts[1]
    assert q["kind"] == "서술형"
    assert q["choices"] == []
    assert figure.points_to_missing(q["question"], q["figure"]) is False


# ---------- T-28 ----------

def test_page_jpeg(sample_bytes):
    img = pageimg.page_jpeg(sample_bytes, 9)
    assert isinstance(img, bytes)
    assert img[:2] == b"\xff\xd8"
    assert pageimg.page_jpeg(sample_bytes, 0) is None
    assert pageimg.page_jpeg(sample_bytes, 21) is None
    assert pageimg.page_jpeg(b"PK\x03\x04" + b"\x00" * 200, 1) is None
    assert pageimg.page_jpeg(b"", 1) is None


# ---------- T-29 ----------

@pytest.mark.parametrize("prio, expected", [
    ({"action": "지금 당장", "exam_pct": 10, "status": "앎"}, "자세히"),       # 지금 당장
    ({"action": "복습만", "exam_pct": 50, "status": "앎"}, "자세히"),          # 출제 50점 이상
    ({"action": "복습만", "exam_pct": 20, "status": "모름"}, "자세히"),        # 모름 + 20점 이상
    ({"action": "다음", "exam_pct": 30, "status": "진단 안 함"}, "보통"),      # 다음
    ({"action": "복습만", "exam_pct": 10, "status": "헷갈림"}, "보통"),        # 헷갈림
    ({"action": "복습만", "exam_pct": 19, "status": "모름"}, "짧게"),          # 모름인데 20점 미만
    ({"action": "복습만", "exam_pct": 49, "status": "앎"}, "짧게"),            # 나머지
])
def test_detail_of_rules(prio, expected):
    assert note.detail_of(prio) == expected


def test_lecture_order_meta_only_goes_last():
    concepts = [{"id": "a", "pages": [1, 20]},     # 메타 페이지만
                {"id": "b", "pages": [1, 5]},
                {"id": "c", "pages": [3, 9]},
                {"id": "d", "pages": []}]
    assert note.lecture_order(concepts, [1, 20]) == ["c", "b", "a", "d"]


def test_short_note_makes_no_ai_call(monkeypatch, analysis, material):
    asked = []
    real = llm.ask_json

    def counting(text, *args, **kwargs):
        asked.append(text[:30])
        return real(text, *args, **kwargs)

    monkeypatch.setattr(llm, "ask_json", counting)
    concept = concept_of(analysis, "c13")
    prio = {"action": "복습만", "exam_pct": 8, "status": "진단 안 함"}
    usage = llm.Usage()
    n = note.make_note(concept, prio, None, analysis["utterances"], material, analysis["meta_pages"], usage=usage)
    assert usage.calls == 0
    assert asked == []
    assert n["detail"] == "짧게"
    assert n["from_ai"] is False
    assert n["summary"] == concept["summary"]
    assert concept["summary"] != ""


def test_detailed_note_calls_ai_once(analysis, material):
    concept = concept_of(analysis, "c5")
    prio = {"action": "지금 당장", "exam_pct": 100, "status": "모름"}
    usage = llm.Usage()
    n = note.make_note(concept, prio, None, analysis["utterances"], material, analysis["meta_pages"], usage=usage)
    assert usage.calls == 1
    assert n["detail"] == "자세히"
    assert n["from_ai"] is True
    assert set(n["source_pages"]) <= set(concept["pages"])


def test_detailed_note_prompt_has_reason_and_professor_quote(analysis):
    concept = concept_of(analysis, "c5")
    prio = {"action": "지금 당장", "exam_pct": 100, "status": "모름"}
    g = {"score": 3, "error_type": "절차 누락", "reason": "전위와 중위 순서를 바꿔 썼다고 채점함."}
    quotes = note.professor_quotes("c5", analysis["utterances"], 5)
    assert len(quotes) >= 1
    text = note.note_prompt(concept, "자세히", prio, g, analysis["utterances"], "=== 페이지 9 ===\n쪽 글")
    assert "전위와 중위 순서를 바꿔 썼다고 채점함." in text
    assert json.dumps(quotes[0]["quote"], ensure_ascii=False)[1:-1] in text
    assert "자세한 정도는 **자세히**" in text


def test_fix_recording_marks_keeps_only_quoted_sentence():
    quotes = [{"quote": "힙 삭제는 시험에 꼭 나옵니다."}]
    text = ('교수님은 "힙 삭제는 시험에 꼭 나옵니다"라고 강조했다(녹음). '
            "루트를 꺼낸 뒤 마지막 노드를 올린다(녹음).")
    out = note.fix_recording_marks(text, quotes)
    assert out.count("(녹음)") == 1
    assert "강조했다(녹음)" in out
    assert "올린다(녹음)" not in out
    assert "루트를 꺼낸 뒤 마지막 노드를 올린다" in out


def test_fix_recording_marks_with_space_before_mark():
    # "(녹음)" 앞에 빈칸을 둔 글도 같은 규칙: 인용이 든 문장의 표시는 남는다
    quotes = [{"quote": "힙 삭제는 시험에 꼭 나옵니다."}]
    text = ('교수님은 "힙 삭제는 시험에 꼭 나옵니다"라고 강조했다 (녹음). '
            "루트를 꺼낸 뒤 마지막 노드를 올린다 (녹음).")
    out = note.fix_recording_marks(text, quotes)
    assert out.count("(녹음)") == 1
    assert "강조했다 (녹음)" in out
    assert "올린다 (녹음)" not in out


def test_fix_recording_marks_no_quotes_removes_all():
    out = note.fix_recording_marks("절차는 한 단계씩 진행한다(녹음).", [])
    assert "(녹음)" not in out
    assert "절차는 한 단계씩 진행한다" in out


# ---------- T-30 ----------

Q_TEXT = "아래 트리에서 전위 순회 순서를 쓰고 <script>alert(1)</script> 이유를 쓰시오."
MY_ANSWER = "내가 쓴 답은 A, C, B 순서다 <script>bad()</script>"
REASON = "왼쪽 서브트리를 먼저 방문하지 않았다고 채점했다."
EXPL_TEXT = "전위 순회는 루트를 먼저 방문한다는 보완 설명 문장이다."
NOTE_TEXT = "요약 노트에만 나오는 순회 정리 문장이다."


def split_state():
    concepts = [{"id": "c1", "name": "이진 트리의 순회", "summary": "순회 한 줄 요약", "pages": [8, 9]}]
    q = diagnose.clean_essay({
        "question": Q_TEXT, "answer": "A, B, D, C 순서다. 루트를 먼저 방문하기 때문이다.",
        "rubric": [{"point": "순서", "score": 6}, {"point": "이유", "score": 4}],
        "source_pages": [9], "figure": {"kind": "tree", "nodes": ["A", "B", "C", "D"], "caption": "예시 트리"},
    }, [8, 9])
    g = diagnose.clean_grading({"rubric_scores": [1, 0], "score": 1, "error_type": "절차 누락", "reason": REASON},
                               q, [8, 9])
    scores = [{"concept_id": "c1", "name": "이진 트리의 순회", "pct": 80}]
    grading = {"c1": g}
    return {
        "material_name": "샘플.pdf", "has_transcript": False, "concepts": concepts, "meta_pages": [],
        "utterances": [], "scores": [], "priorities": priority.compute_priorities(scores, grading),
        "questions": {"c1": q},
        "given": {"c1": {"answer": MY_ANSWER, "dont_know": False, "choice": None, "guessed": False}},
        "confusion": {}, "grading": grading,
        "explanations": {"c1": {"concept_id": "c1", "my_gap": "방문 순서를 놓쳤다.", "explanation": EXPL_TEXT,
                                "check_pages": [9], "source_pages": [9], "not_found": False,
                                "not_found_note": None, "confusion_reply": None}},
        "notes": {"c1": {"concept_id": "c1", "detail": "자세히", "from_ai": True, "summary": NOTE_TEXT,
                         "key_points": ["핵심 <script>x()</script>"], "pitfalls": [], "source_pages": [8]}},
    }


def test_export_split_question_once_and_same_card():
    state = split_state()
    assert state["grading"]["c1"]["status"] == "모름"
    study = export.study_html(state)
    notes = export.notes_html(state)

    assert study.count(esc(Q_TEXT)) == 1
    assert esc(Q_TEXT) not in notes

    cards = study.split('<div class="bn-card">')
    assert len(cards) == 2  # 카드 하나
    card = cards[1].split("<h2>")[0]
    assert esc(MY_ANSWER) in card
    assert REASON in card
    assert EXPL_TEXT in card

    assert study.count("data:image/svg+xml") == 1
    assert "data:image/svg+xml" not in notes


def test_export_split_no_page_image_and_note_only_in_notes_file():
    state = split_state()
    study = export.study_html(state)
    notes = export.notes_html(state)
    for doc in (study, notes):
        assert "image/jpeg" not in doc
        assert "#pg-" not in doc
        assert "<script" not in doc
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in study
    assert "&lt;script&gt;bad()&lt;/script&gt;" in study
    assert "&lt;script&gt;x()&lt;/script&gt;" in notes
    assert notes.count(NOTE_TEXT) == 1
    assert NOTE_TEXT not in study
    assert EXPL_TEXT not in notes
