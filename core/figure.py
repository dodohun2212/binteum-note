"""F08 문제 그림(트리·배열·표) 검사와 그리기, 페이지·그림을 가리키는 문제 찾기."""
import base64
import math
import re

from core.html import esc

MAX_NODES = 31
MAX_COLS = 6
MAX_ROWS = 10


def _s(v) -> str:
    return str(v).strip()


def clean_figure(raw):
    """형식이 맞는 그림만 돌려준다. 틀리면 None(그림 없이)."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    caption = _s(raw.get("caption")) if raw.get("caption") else ""
    if kind == "tree":
        nodes = raw.get("nodes")
        if not isinstance(nodes, list):
            return None
        nodes = [None if n is None or _s(n) in ("", "null") else _s(n) for n in nodes]
        while nodes and nodes[-1] is None:
            nodes.pop()
        if not nodes or len(nodes) > MAX_NODES or nodes[0] is None:
            return None
        for i in range(1, len(nodes)):
            if nodes[i] is not None and nodes[(i - 1) // 2] is None:
                return None  # 부모 없는 노드
        return {"kind": "tree", "nodes": nodes, "caption": caption}
    if kind == "array":
        items = raw.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_NODES:
            return None
        start = raw.get("start")
        start = 1 if start in (1, "1") else 0
        return {"kind": "array", "items": ["" if v is None else _s(v) for v in items],
                "start": start, "caption": caption}
    if kind == "table":
        header, rows = raw.get("header"), raw.get("rows")
        if not isinstance(header, list) or not isinstance(rows, list):
            return None
        if not header or len(header) > MAX_COLS or not rows or len(rows) > MAX_ROWS:
            return None
        clean_rows = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(header):
                return None  # 열 수가 다른 표
            clean_rows.append(["" if v is None else _s(v) for v in row])
        return {"kind": "table", "header": [_s(h) for h in header], "rows": clean_rows, "caption": caption}
    return None


def to_text(fig) -> str:
    """채점(03-B)과 보완 설명(04)에 넣는 글."""
    if not fig:
        return ""
    cap = f"{fig['caption']}: " if fig.get("caption") else ""
    if fig["kind"] == "tree":
        nodes = ", ".join("null" if n is None else n for n in fig["nodes"])
        return f"{cap}이진 트리(레벨 순서, 빈자리는 null): [{nodes}]"
    if fig["kind"] == "array":
        return f"{cap}배열(인덱스 {fig['start']}부터): [{', '.join(fig['items'])}]"
    rows = " / ".join(" | ".join(r) for r in fig["rows"])
    return f"{cap}표(열: {' | '.join(fig['header'])}): {rows}"


def tree_svg(fig) -> str:
    """트리를 SVG로. 밝은·어두운 화면 모두에서 보이게 흰 바탕과 고정 색을 쓴다."""
    nodes = fig["nodes"]
    depth = int(math.log2(len(nodes))) + 1
    width = max(260, (2 ** (depth - 1)) * 54)
    height = depth * 62 + 16

    def pos(i):
        d = int(math.log2(i + 1))
        k = i + 1 - 2 ** d
        return (k + 0.5) / (2 ** d) * width, 30 + d * 62

    lines, circles = [], []
    for i, node in enumerate(nodes):
        if node is None:
            continue
        x, y = pos(i)
        if i > 0:
            px, py = pos((i - 1) // 2)
            lines.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                         f'stroke="#64748b" stroke-width="1.6"/>')
        size = 14 if len(node) <= 3 else 11
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="19" fill="#ffffff" stroke="#2563eb" '
                       f'stroke-width="2"/><text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" '
                       f'font-size="{size}" font-family="sans-serif" fill="#111827">{esc(node)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" rx="10" fill="#ffffff"/>'
            + "".join(lines) + "".join(circles) + "</svg>")


def to_html(fig) -> str:
    """화면·내려받기에 넣는 그림. st.html이 <svg>를 지우므로 트리는 data URI <img>로 넣는다."""
    if not fig:
        return ""
    cap = f'<div class="bn-fig-cap">{esc(fig["caption"])}</div>' if fig.get("caption") else ""
    if fig["kind"] == "tree":
        data = base64.b64encode(tree_svg(fig).encode("utf-8")).decode("ascii")
        alt = esc(to_text(fig)).replace('"', "&quot;")
        body = f'<img alt="{alt}" src="data:image/svg+xml;base64,{data}">'
    elif fig["kind"] == "array":
        cells = "".join(f"<td>{esc(v)}</td>" for v in fig["items"])
        idx = "".join(f"<td>{fig['start'] + i}</td>" for i in range(len(fig["items"])))
        body = f'<table><tr>{cells}</tr><tr class="bn-idx">{idx}</tr></table>'
    else:
        head = "".join(f"<th>{esc(h)}</th>" for h in fig["header"])
        rows = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in r) + "</tr>" for r in fig["rows"])
        body = f"<table><tr>{head}</tr>{rows}</table>"
    return f'<div class="bn-fig">{cap}{body}</div>'


_PAGE_REF = re.compile(r"p\.\s?\d+|\d+\s?쪽|\d+\s?페이지|슬라이드\s?\d+")
_FIG_REF = re.compile(r"그림|(?:오른쪽|왼쪽|위|위의|아래|다음)\s?(?:트리|표)|아래\s?배열")


def points_to_missing(question_text: str, fig) -> bool:
    """문제 글이 페이지를 가리키거나, 그림 없이 '그림·위 트리'를 가리키면 참(다시 만들 문제)."""
    text = question_text or ""
    if _PAGE_REF.search(text):
        return True
    return fig is None and bool(_FIG_REF.search(text))
