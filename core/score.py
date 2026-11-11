"""F07 출제 가능성 점수(8장). AI를 부르지 않는 순수 함수다."""
import re

# 8.1 가중치 표 (v0). 바꾸면 버전을 올리고 README에 적는다.
WEIGHTS = {
    "objective": 3.0,        # 학습목표에 있음
    "page": 1.0,             # 본문 쪽당
    "page_max": 4,           # 본문 쪽수 상한
    "example": 1.5,          # 예제·그림으로 과정 설명
    "exercise": 2.0,         # 연습문제에 포함(한 번만)
    "emphasis": 1.0,         # 강조 × (strength/3), 발화마다
    "exam_hint": 1.5,        # 시험 암시 × (strength/3)
    "mistake_warning": 0.7,  # 실수 경고 × (strength/3)
    "exercise_hint": 1.0,    # 연습문제 지목 × (strength/3)
    "question": 0.5,         # 학우 질문, 질문마다
    "deferral": -2.5,        # 다음에 다룸, 발화마다
    "skip": -1.0,            # 가볍게 넘어감, 발화마다
}
WEIGHTS_VERSION = "v0"

TYPE_LABEL = {
    "emphasis": "강조",
    "exam_hint": "시험 암시",
    "mistake_warning": "실수 경고",
    "exercise_hint": "연습문제 지목",
    "question": "학우 질문",
    "deferral": "다음에 다룸",
    "skip": "가볍게 넘어감",
}
_SCALED = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint")
_FLAT = ("question", "deferral", "skip")

_META_WORDS = ("목차", "학습 목표", "학습목표", "연습문제", "연습 문제", "요약", "참고문헌", "차례")
_SECTION_NO = re.compile(r"^\s*(?:제\s*)?\d+(?:\.\d+)*[.)]?\s+")
_TOC_LINE = re.compile(r"^\s*\d+\.\d+\s+\S*[^\d\s.]")


def is_meta_text(text: str) -> bool:
    """8.3 코드 규칙 ①(첫 줄이 '목차'·'요약' 등으로 시작)과 ②(절 번호 줄이 3줄 이상)."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    first = _SECTION_NO.sub("", lines[0]).lstrip("■□▶●·-–— \t")
    for word in _META_WORDS:
        if first.startswith(word):
            rest = first[len(word):]
            # "요약하면 …"처럼 본문 문장으로 이어지면 메타가 아니다
            if not rest or not ("가" <= rest[0] <= "힣"):
                return True
    toc = sum(1 for ln in lines[:12] if _TOC_LINE.match(ln))
    return toc >= 3


def find_meta_pages(pages: list, result: dict) -> list:
    """메타 페이지 = AI가 준 것 + 코드 규칙 ①② + 1쪽의 합집합."""
    n_pages = len(pages)
    meta = {1}
    for n in (result or {}).get("meta_pages") or []:
        if isinstance(n, int):
            meta.add(n)
    for key in ("objectives_page", "exercise_page"):
        n = (result or {}).get(key)
        if isinstance(n, int):
            meta.add(n)
    for p in pages:
        if is_meta_text(p.get("text", "")):
            meta.add(p["n"])
    return sorted(n for n in meta if 1 <= n <= max(n_pages, 1))


def _short(quote: str, n: int = 28) -> str:
    quote = (quote or "").strip()
    return quote if len(quote) <= n else quote[:n] + "…"


def compute_scores(concepts: list, utterances: list, meta_pages: list) -> dict:
    """개념마다 raw·pct·근거 목록을 만들고 순위대로 돌려준다(6.4)."""
    meta = set(meta_pages or [])
    rows = []
    for c in concepts:
        reasons = []
        body = [p for p in c.get("pages", []) if p not in meta]
        if c.get("in_objectives"):
            reasons.append({"kind": "objective", "points": WEIGHTS["objective"], "label": "학습목표"})
        if body:
            n = min(len(body), WEIGHTS["page_max"])
            reasons.append({"kind": "page", "points": n * WEIGHTS["page"], "label": f"본문 {len(body)}쪽"})
        if c.get("has_example"):
            reasons.append({"kind": "example", "points": WEIGHTS["example"], "label": "예제"})
        if c.get("has_exercise"):
            nums = " ".join(str(n) for n in c.get("exercise_numbers") or [])
            reasons.append({"kind": "exercise", "points": WEIGHTS["exercise"],
                            "label": ("연습문제 " + nums).strip()})
        for u in utterances or []:
            if u.get("concept_id") != c["id"]:
                continue
            kind = u.get("type")
            if kind in _SCALED:
                strength = max(1, min(3, int(u.get("strength") or 1)))
                points = WEIGHTS[kind] * strength / 3
            elif kind in _FLAT:
                strength = max(1, min(3, int(u.get("strength") or 1)))
                points = WEIGHTS[kind]
            else:
                continue  # 모르는 유형은 무시
            reasons.append({"kind": kind, "points": round(points, 4), "strength": strength,
                            "quote": u.get("quote", ""),
                            "label": f"{TYPE_LABEL[kind]}: “{_short(u.get('quote', ''))}”"})
        raw = round(sum(r["points"] for r in reasons), 4)
        rows.append({"concept_id": c["id"], "name": c["name"], "raw": raw, "pct": 0,
                     "body_pages": body, "first_page": min(c.get("pages") or [10 ** 6]),
                     "reasons": reasons})
    max_raw = max([r["raw"] for r in rows] + [0])
    for r in rows:
        r["pct"] = int(round(max(r["raw"], 0) / max_raw * 100)) if max_raw > 0 else 0
    rows.sort(key=lambda r: (-r["pct"], -len(r["body_pages"]), r["first_page"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"max_raw": max_raw, "scores": rows}


def badges(score_row: dict) -> list:
    """S02·내려받기에 쓰는 근거 배지 [(글, 감점 여부)]. 같은 발화 유형은 ×n으로 묶는다."""
    out = []
    counts = {}
    for r in score_row.get("reasons", []):
        kind = r["kind"]
        if kind in ("objective", "page", "example", "exercise"):
            out.append((r["label"], False))
        else:
            counts[kind] = counts.get(kind, 0) + 1
    for kind in ("emphasis", "exam_hint", "mistake_warning", "exercise_hint", "question", "deferral", "skip"):
        n = counts.get(kind, 0)
        if n:
            label = TYPE_LABEL[kind] + (f" ×{n}" if n > 1 else "")
            out.append((label, kind in ("deferral", "skip")))
    return out
