"""T-08~T-11: 자료 읽기(PDF·PPTX), 스캔본·형식·크기 검사, 개인정보 마스킹."""
import io

import pytest

from config import MAX_MATERIAL_MB
from core import extract


def _pptx_bytes() -> bytes:
    """슬라이드 3장(둘째 장에 표)짜리 pptx를 메모리에 만든다."""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    blank = prs.slide_layouts[6]
    s1 = prs.slides.add_slide(blank)
    s1.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text_frame.text = "첫 장 트리 소개"
    s2 = prs.slides.add_slide(blank)
    table = s2.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(5), Inches(2)).table
    table.cell(0, 0).text = "연산"
    table.cell(0, 1).text = "시간"
    table.cell(1, 0).text = "힙삽입셀"
    table.cell(1, 1).text = "로그엔셀"
    s3 = prs.slides.add_slide(blank)
    s3.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1)).text_frame.text = "셋째 장 정리"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _blank_pdf_bytes(n: int = 3) -> bytes:
    """글자가 하나도 없는 PDF(빈 쪽 n장)."""
    import pymupdf

    doc = pymupdf.open()
    for _ in range(n):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


# ---------- T-08 샘플 PDF ----------

def test_t08_sample_pdf_has_20_pages(material):
    assert material["kind"] == "pdf"
    assert material["n_pages"] == 20
    assert len(material["pages"]) == 20
    assert [p["n"] for p in material["pages"]] == list(range(1, 21))


def test_t08_every_page_has_text(material):
    for p in material["pages"]:
        assert p["text"].strip(), f"{p['n']}쪽이 비어 있음"
        assert p["text"] != extract.EMPTY_PAGE, f"{p['n']}쪽에 글자가 없음"


def test_t08_page_15_mentions_upheap(material):
    assert "업힙" in material["pages"][14]["text"]


# ---------- T-09 PPTX ----------

def test_t09_pptx_three_slides_with_table_cells():
    m = extract.extract("a.pptx", _pptx_bytes())
    assert m["kind"] == "pptx"
    assert m["n_pages"] == 3
    assert len(m["pages"]) == 3
    assert "첫 장 트리 소개" in m["pages"][0]["text"]
    for cell in ("연산", "시간", "힙삽입셀", "로그엔셀"):
        assert cell in m["pages"][1]["text"]
    assert "셋째 장 정리" in m["pages"][2]["text"]


# ---------- T-10 스캔본·형식·크기 ----------

def test_t10_scan_pdf_is_e03():
    with pytest.raises(extract.ScanPDFError) as info:
        extract.extract("scan.pdf", _blank_pdf_bytes(3))
    assert info.value.code == "E-03"


def test_t10_hwp_is_e01():
    with pytest.raises(extract.BadFormatError) as info:
        extract.extract("a.hwp", b"hwp")
    assert info.value.code == "E-01"
    with pytest.raises(extract.BadFormatError):
        extract.check_material("a.hwp", 10)


def test_t10_too_big_is_e02():
    limit = MAX_MATERIAL_MB * 1024 * 1024
    assert MAX_MATERIAL_MB == 30
    with pytest.raises(extract.TooBigError) as info:
        extract.check_material("a.pdf", limit + 1)
    assert info.value.code == "E-02"
    # 딱 상한까지는 통과
    assert extract.check_material("a.pdf", limit) == "pdf"
    assert extract.check_material("a.PPTX", 100) == "pptx"


# ---------- T-11 마스킹 ----------

def test_t11_mask_four_kinds():
    out = extract.mask("학번 2021136001, 010-1234-5678, a@b.ac.kr, 900101-1234567")
    assert out.count("[마스킹]") == 4
    for secret in ("2021136001", "010-1234-5678", "1234-5678", "a@b.ac.kr", "900101", "1234567"):
        assert secret not in out
    assert out.startswith("학번")


def test_t11_mask_keeps_plain_numbers():
    text = "INT_MAX = 2147483647, n = 10000000, 20240315"
    assert extract.mask(text) == text
