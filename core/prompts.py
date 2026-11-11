"""prompts/*.md 읽기와 {{자리}} 채우기. 프롬프트 문장은 코드에 두지 않는다(BR-10)."""
import re
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 버전을 바꿀 때는 새 파일을 만들고 이 표에서 고른다.
FILES = {
    "01": "01_개념추출_v1.md",
    "02": "02_강조발화_v1.md",
    "03A": "03A_진단문제_v1.md",
    "03B": "03B_채점_v1.md",
    "03C": "03C_객관식_v1.md",
    "04": "04_보완설명_v1.md",
    "05": "05_요약노트_v1.md",
}

_SLOT = re.compile(r"\{\{([A-Z_]+)\}\}")


@lru_cache(maxsize=None)
def load(key: str) -> str:
    return (PROMPT_DIR / FILES[key]).read_text(encoding="utf-8")


def fill(key: str, **slots) -> str:
    """프롬프트 파일의 {{자리}}를 한 번에 채운다. 채운 글 안의 {{…}}는 다시 건드리지 않는다."""
    template = load(key)
    missing = [m for m in _SLOT.findall(template) if m not in slots]
    if missing:
        raise KeyError(f"프롬프트 {key}의 자리를 채우지 않음: {sorted(set(missing))}")
    return _SLOT.sub(lambda m: str(slots[m.group(1)]), template)
