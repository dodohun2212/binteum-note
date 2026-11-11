"""T-49 결과 예시 만들기·마크다운 변환, T-50 README 안내 문구와 채점 말투."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import export, prompts  # noqa: E402
from scripts import make_example  # noqa: E402

FILES = ["README.md", "공부순서_오답노트.html", "공부순서_오답노트.md", "요약노트.html", "요약노트.md"]


def test_run_writes_five_files_with_all_statuses(tmp_path):
    """가짜 AI로 앱과 같은 순서를 돌리면 파일 5개가 생기고 앎·헷갈림·모름이 모두 나온다."""
    stats = make_example.run(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == FILES
    assert stats["files"] == FILES
    assert all(stats["status"][s] >= 1 for s in ("앎", "헷갈림", "모름"))
    assert stats["concepts"] == 13
    assert sum(stats["failed"].values()) == 0
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "단계별 시간" in readme
    assert "진단 문제 11개" in readme


def test_markdown_has_no_tags_or_image_data(tmp_path):
    make_example.run(tmp_path)
    for name in ("공부순서_오답노트.md", "요약노트.md"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "<" not in text
        assert "data:image" not in text
        assert text.startswith("# 빈틈노트")
    study = (tmp_path / "공부순서_오답노트.md").read_text(encoding="utf-8")
    assert "## 1. 공부 순서" in study
    assert "(p." in study
    assert "`모름`" in study
    assert "(그림) " in study


def test_html_to_md_converts_pieces():
    html = ('<style>.x{color:red}</style><h2>제목</h2><p>글 <span class="bn-chip">p.5</span></p>'
            '<p><span class="bn-badge bn-bad">모름</span></p><ul><li>하나</li></ul>'
            '<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>'
            '<img alt="트리 [A, B]" src="data:image/svg+xml;base64,AAAA">')
    md = make_example.html_to_md(html)
    assert "## 제목" in md
    assert "(p.5)" in md
    assert "`모름`" in md
    assert "- 하나" in md
    assert "| a | b |" in md
    assert "| 1 | 2 |" in md
    assert "(그림) 트리 [A, B]" in md
    assert "data:image" not in md
    assert "color:red" not in md
    assert "<" not in md


def test_from_html_makes_markdown_and_readme(tmp_path):
    """배포 앱에서 내려받은 HTML 2개로도 결과 예시를 만든다."""
    study, notes = tmp_path / "a.html", tmp_path / "b.html"
    study.write_text(export.study_html({}), encoding="utf-8")
    notes.write_text(export.notes_html({}), encoding="utf-8")
    out = tmp_path / "out"
    assert make_example.from_html(study, notes, out) == FILES
    assert "내려받은 HTML" in (out / "README.md").read_text(encoding="utf-8")
    assert "요약 노트 없음" in (out / "요약노트.md").read_text(encoding="utf-8")


def test_readme_guides_and_grading_tone():
    """T-50 README에 잠든 앱 깨우는 법과 점수 설명이 있고, 채점 프롬프트는 "~다" 말투다."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Yes, get this app back up!" in readme
    assert "AI가 찾은 신호가 같으면" in readme
    assert "출제를 보장하지 않습니다" in readme
    assert "세션 메모리에만" not in readme
    assert '"~다"' in prompts.load("03B")
