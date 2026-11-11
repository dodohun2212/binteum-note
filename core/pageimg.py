"""F09 강의자료 PDF 한 쪽 → 그림(JPEG). 화면에서만 쓰고 내려받는 파일에는 넣지 않는다."""


def page_jpeg(data, n: int, width: int = 900):
    """PDF의 n쪽(1부터)을 가로 width px JPEG로. PDF가 아니거나 쪽이 없으면 None."""
    if not data or not bytes(data[:5]).startswith(b"%PDF"):
        return None
    try:
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            if not 1 <= n <= len(doc):
                return None
            page = doc[n - 1]
            zoom = width / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return pix.tobytes("jpeg")
    except Exception:
        return None
