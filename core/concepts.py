"""F05 개념 추출 (AI 호출 1) + 결과 검사."""
import re

from core import llm, prompts
from core.extract import pages_text
from core.schemas import Concept

CALL1_MAX_TOKENS = 8000


class NoConceptsError(Exception):
    code = "E-09"
    message = "이 자료에서 개념을 찾지 못했어요. 강의 슬라이드나 교재 한 장인지 확인해 주세요"

    def __str__(self):
        return self.message


def to_ints(value) -> list:
    """쪽 번호를 숫자로 읽는다: 5, 5.0, "5", "p.5", "3-4"(3과 4)."""
    if value is None or isinstance(value, bool):
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    out = []
    for v in value:
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            out.append(int(v))
            continue
        text = str(v)
        rng = re.search(r"(\d+)\s*[-~–]\s*(\d+)", text)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if a <= b and b - a < 50:
                out.extend(range(a, b + 1))
                continue
        out.extend(int(float(n)) for n in re.findall(r"\d+(?:\.0+)?", text))
    return out


def _as_bool(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "예")
    return bool(v)


def _in_range(nums, n_pages) -> list:
    out = []
    for n in nums:
        if 1 <= n <= n_pages and n not in out:
            out.append(n)
    return sorted(out)


def clean_concepts(raw, n_pages: int) -> dict:
    """호출 1의 답을 항목마다 검사한다. 형식이 틀린 항목만 버리고 나머지는 살린다."""
    if not isinstance(raw, dict):
        raise NoConceptsError()
    items = raw.get("concepts")
    if not isinstance(items, list):
        items = []
    out, ids, names = [], set(), set()
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name or name in names:
            continue
        cid = item.get("id")
        cid = str(cid).strip() if cid not in (None, "") else f"c{i}"
        k = i
        while cid in ids:
            k += 1
            cid = f"c{k}"
        quote = item.get("objective_quote")
        keywords = item.get("keywords")
        try:
            concept = Concept(
                id=cid, name=name, summary=str(item.get("summary") or "").strip(),
                pages=_in_range(to_ints(item.get("pages")), n_pages),
                in_objectives=_as_bool(item.get("in_objectives")),
                objective_quote=str(quote).strip() if quote not in (None, "", "null") else None,
                has_example=_as_bool(item.get("has_example")),
                has_exercise=_as_bool(item.get("has_exercise")),
                exercise_numbers=[n for n in to_ints(item.get("exercise_numbers")) if n > 0],
                keywords=[str(k).strip() for k in keywords if str(k).strip()] if isinstance(keywords, list) else [],
            )
        except Exception:
            continue
        ids.add(cid)
        names.add(name)
        out.append(concept.model_dump())
    if not out:
        raise NoConceptsError()

    def one(key):
        nums = _in_range(to_ints(raw.get(key)), n_pages)
        return nums[0] if nums else None

    return {"objectives_page": one("objectives_page"), "exercise_page": one("exercise_page"),
            "meta_pages": _in_range(to_ints(raw.get("meta_pages")), n_pages), "concepts": out}


def extract_concepts(material: dict, usage=None) -> dict:
    """자료 전체를 보내 개념 목록을 받는다(호출 1만 자료 전체)."""
    text = prompts.fill("01", MATERIAL=pages_text(material["pages"]))
    raw = llm.ask_json(text, CALL1_MAX_TOKENS, thinking=True, usage=usage)
    return clean_concepts(raw, material["n_pages"])
