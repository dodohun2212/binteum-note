"""인용 쪽 번호 검사. 범위 밖 번호는 코드가 지운다."""
import re

_CITE = re.compile(r"\s?\((p\.[^()]{0,40})\)")


def keep_pages(pages, valid) -> list:
    """입력한 페이지 안에 있는 번호만 남긴다(중복 없이, 순서 유지)."""
    valid = set(int(v) for v in valid)
    out = []
    for p in pages or []:
        try:
            n = int(p)
        except (TypeError, ValueError):
            continue
        if n in valid and n not in out:
            out.append(n)
    return out


def strip_bad_cites(text, valid) -> str:
    """본문 속 (p.n) 표시 중 근거 페이지 밖인 것만 지운다."""
    if not text:
        return ""
    valid = set(int(v) for v in valid)

    def fix(m):
        nums = [int(n) for n in re.findall(r"\d+", m.group(1))]
        if not nums:
            return m.group(0)
        good = [n for n in nums if n in valid]
        if len(good) == len(nums):
            return m.group(0)
        if not good:
            return ""
        lead = " " if m.group(0).startswith(" ") else ""
        return lead + "(" + ", ".join(f"p.{n}" for n in good) + ")"

    return _CITE.sub(fix, str(text))
