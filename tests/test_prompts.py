"""T-12, T-13: 프롬프트 자리 채우기와 JSON 잘라내기."""
import re

import pytest

from core import llm, prompts

_SLOT = re.compile(r"\{\{([A-Z_0-9]+)\}\}")


def _slots(key: str) -> set:
    """프롬프트 파일을 읽어 자리 이름을 모은다."""
    text = (prompts.PROMPT_DIR / prompts.FILES[key]).read_text(encoding="utf-8")
    return set(_SLOT.findall(text))


# ---------- T-12 프롬프트 채우기 ----------

def test_t12_fill_01_with_short_material():
    out = prompts.fill("01", MATERIAL="짧은 자료")
    assert "{{MATERIAL}}" not in out
    assert "짧은 자료" in out


def test_t12_seven_prompt_files_exist():
    assert set(prompts.FILES) == {"01", "02", "03A", "03B", "03C", "04", "05"}
    for key, name in prompts.FILES.items():
        assert (prompts.PROMPT_DIR / name).is_file(), key


@pytest.mark.parametrize("key", ["01", "02", "03A", "03B", "03C", "04", "05"])
def test_t12_all_slots_filled(key):
    names = _slots(key)
    assert names, f"프롬프트 {key}에 자리가 하나도 없음"
    values = {name: f"채운값_{name.lower()}" for name in names}
    out = prompts.fill(key, **values)
    assert "{{" not in out
    assert "}}" not in out
    for value in values.values():
        assert value in out


@pytest.mark.parametrize("key", ["02", "03A", "03B", "03C", "04", "05"])
def test_t12_missing_slot_raises_keyerror(key):
    names = sorted(_slots(key))
    values = {name: "값" for name in names[1:]}  # 첫 자리를 빠뜨린다
    with pytest.raises(KeyError):
        prompts.fill(key, **values)


def test_t12_missing_only_slot_raises_keyerror():
    with pytest.raises(KeyError):
        prompts.fill("01")


def test_t12_filled_text_is_not_filled_again():
    # 채운 글 안에 {{…}}가 있어도 다시 바꾸지 않는다
    out = prompts.fill("02", CONCEPTS_JSON="{{TRANSCRIPT}}", TRANSCRIPT="대본글자")
    assert out.count("{{TRANSCRIPT}}") == 1
    assert "대본글자" in out


# ---------- T-13 JSON 잘라내기 ----------

def test_t13_extract_json_from_mixed_text():
    assert llm.extract_json('설명입니다 {"a":1} 끝') == {"a": 1}


def test_t13_extract_json_nested():
    assert llm.extract_json('```json\n{"a": {"b": [1, 2]}}\n```') == {"a": {"b": [1, 2]}}


@pytest.mark.parametrize("text", ["JSON이 없는 글입니다", "", "{ 깨진 글 }"])
def test_t13_no_json_raises_valueerror(text):
    with pytest.raises(ValueError):
        llm.extract_json(text)
