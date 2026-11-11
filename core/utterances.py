"""F06 강조 발화 찾기 (AI 호출 2) + 인용 검사."""
import json
import re

from core import llm, prompts
from core.extract import mask
from core.schemas import Utterance

CALL2_MAX_TOKENS = 6000
TYPES = ("emphasis", "exam_hint", "mistake_warning", "exercise_hint", "deferral", "skip")


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _fix_id(value, ids):
    """개념 id를 글자로 맞춘다. 숫자 5는 "5" 또는 "c5"로 읽는다. 목록에 없으면 None."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if isinstance(value, float) and value == int(value):
        text = str(int(value))
    if text in ids:
        return text
    if "c" + text in ids:
        return "c" + text
    return None


def clean_utterances(raw, transcript: str, concepts: list) -> list:
    """호출 2의 답 검사. 대본에 실제로 있는 문장만, 대본에 나온 횟수까지만 남긴다."""
    items = raw.get("utterances") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    ids = {c["id"] for c in concepts}
    names = {c["id"]: c["name"] for c in concepts}
    body = _norm(transcript)
    out, used = [], {}
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        key = _norm(quote)
        if not key or key not in body:
            continue  # 대본에 없는 인용은 버린다
        kind = item.get("type")
        if kind not in TYPES:
            continue
        try:
            strength = max(1, min(3, int(round(float(item.get("strength", 1))))))
        except (TypeError, ValueError):
            strength = 1
        cid = _fix_id(item.get("concept_id"), ids)
        targets = [cid]
        if cid is None and kind == "exercise_hint":
            # "4번 5번은 꼭 풀어보세요" → 그 번호의 연습문제를 가진 개념마다 하나씩
            nums = {int(n) for n in re.findall(r"(\d+)\s*번", quote)}
            hit = [c["id"] for c in concepts if nums & set(c.get("exercise_numbers") or [])]
            targets = hit or [None]
        limit = body.count(key)
        for target in targets:
            if used.get((key, target), 0) >= limit:
                continue  # 한 번 한 말을 여러 번 적어 점수를 부풀리지 못하게
            used[(key, target)] = used.get((key, target), 0) + 1
            name = names.get(target) or str(item.get("concept_name") or "").strip()
            out.append(Utterance(concept_id=target, concept_name=name, quote=quote,
                                 type=kind, strength=strength).model_dump())
    return out


def find_utterances(transcript: str, concepts: list, usage=None) -> list:
    """대본 전체 + 개념 목록(id, name, summary, keywords만)을 보낸다. 대본이 없으면 부르지 않는다."""
    if not transcript or not transcript.strip():
        return []
    masked = mask(transcript)
    brief = [{"id": c["id"], "name": c["name"], "summary": c.get("summary", ""),
              "keywords": c.get("keywords", [])} for c in concepts]
    text = prompts.fill("02", CONCEPTS_JSON=json.dumps(brief, ensure_ascii=False, indent=1),
                        TRANSCRIPT=masked)
    raw = llm.ask_json(text, CALL2_MAX_TOKENS, thinking=True, usage=usage)
    return clean_utterances(raw, masked, concepts)


def concept_key(concepts: list) -> str:
    """호출 2 캐시 키에 넣는 개념 목록(JSON)."""
    return json.dumps([[c["id"], c["name"]] for c in concepts], ensure_ascii=False)
