"""F01 형식 검사, F02 PDF/PPTX → 페이지별 텍스트, F04 개인정보 마스킹."""
import hashlib
import io
import re

from config import MAX_AUDIO_MB, MAX_MATERIAL_MB, MAX_PAGES

EMPTY_PAGE = "(글자 없음)"
MASK = "[마스킹]"


class ExtractError(Exception):
    """자료를 읽지 못함. code는 9장 에러 번호."""

    code = "E-01"
    message = "PDF나 PPTX만 올릴 수 있어요. 한글(hwp)은 파일 → PDF로 저장해 주세요"

    def __str__(self):
        return self.message


class BadFormatError(ExtractError):
    code = "E-01"


class TooBigError(ExtractError):
    code = "E-02"
    message = "파일이 너무 커요(최대 30MB). 한 장만 따로 저장해 올려 주세요"


class ScanPDFError(ExtractError):
    code = "E-03"
    message = "이 PDF는 글자가 그림으로 들어 있어 읽을 수 없어요. 글자가 선택되는 PDF를 올려 주세요"


class AudioError(ExtractError):
    code = "E-04"
    message = "녹음은 m4a/mp3/wav 25MB까지예요. 길면 앞부분만 잘라 올리거나 대본 붙여넣기를 써 주세요"


def file_kind(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def check_material(name: str, size: int) -> str:
    """강의자료 형식·크기 검사. 통과하면 'pdf' 또는 'pptx'."""
    kind = file_kind(name)
    if kind not in ("pdf", "pptx"):
        raise BadFormatError()
    if size > MAX_MATERIAL_MB * 1024 * 1024:
        raise TooBigError()
    return kind


def check_audio(name: str, size: int) -> str:
    kind = file_kind(name)
    if kind not in ("m4a", "mp3", "wav") or size > MAX_AUDIO_MB * 1024 * 1024:
        raise AudioError()
    return kind


def make_run_id(data: bytes, transcript: str = "") -> str:
    """파일 내용 해시 12자. 캐시 키로 쓴다."""
    h = hashlib.sha256(data)
    h.update((transcript or "").encode("utf-8"))
    return h.hexdigest()[:12]


def _pdf_pages(data: bytes) -> list:
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_text() for page in doc]


def _shape_texts(shape) -> list:
    out = []
    if getattr(shape, "shape_type", None) == 6 and hasattr(shape, "shapes"):  # 묶음 도형
        for sub in shape.shapes:
            out.extend(_shape_texts(sub))
        return out
    if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
        out.append(shape.text_frame.text)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    out.append(cell.text)
    return out


def _pptx_pages(data: bytes) -> list:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        texts = []
        for shape in slide.shapes:
            texts.extend(_shape_texts(shape))
        pages.append("\n".join(texts))
    return pages


def extract(name: str, data: bytes) -> dict:
    """PDF/PPTX 바이트 → material(6.1). 글자는 가린 뒤 돌려준다."""
    kind = check_material(name, len(data))
    try:
        texts = _pdf_pages(data) if kind == "pdf" else _pptx_pages(data)
    except ExtractError:
        raise
    except Exception as e:  # 깨진 파일
        raise BadFormatError() from e
    total = len(texts)
    if total == 0:
        raise ScanPDFError()
    empty = sum(1 for t in texts if not t.strip())
    if empty / total >= 0.8:
        raise ScanPDFError()
    texts = texts[:MAX_PAGES]
    pages = [{"n": i + 1, "text": mask(t.strip()) if t.strip() else EMPTY_PAGE} for i, t in enumerate(texts)]
    return {
        "name": name,
        "kind": kind,
        "n_pages": len(pages),
        "total_pages": total,
        "chars": sum(len(p["text"]) for p in pages),
        "pages": pages,
    }


def pages_text(pages: list, nums=None) -> str:
    """AI에 보낼 한 덩어리 글. 페이지마다 '=== 페이지 n ===' 줄을 붙인다."""
    want = None if nums is None else set(int(n) for n in nums)
    parts = []
    for p in pages:
        if want is None or p["n"] in want:
            parts.append(f"=== 페이지 {p['n']} ===\n{p['text']}")
    return "\n\n".join(parts)


_RRN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}|0\d{1,2}-\d{3,4}-\d{4})(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_STUDENT = re.compile(r"((?:학번|학생번호|[Ss]tudent\s?ID|\bID)[^\d\n]{0,10}?)(?<!\d)\d{8,10}(?!\d)")


def mask(text: str) -> str:
    """학번·주민등록번호·전화번호·이메일을 [마스킹]으로. 사람 이름은 건드리지 않는다.

    학번은 바로 앞에 '학번' 같은 말이 있는 숫자만 가린다(강의 내용 속 큰 숫자를 망가뜨리지 않게).
    """
    if not text:
        return text or ""
    out = _RRN.sub(MASK, text)
    out = _PHONE.sub(MASK, out)
    out = _EMAIL.sub(MASK, out)
    out = _STUDENT.sub(lambda m: m.group(1) + MASK, out)
    return out
