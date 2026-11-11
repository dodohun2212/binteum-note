"""BINTM_FAKE_AI=1일 때 실제 AI 대신 답한다. 키 없이 화면 확인·테스트에 쓴다.

호출 1·2는 tests/fixtures의 저장된 결과, 호출 3~5는 정해진 모양의 답이다.
샘플 자료가 아니면 내용이 맞지 않는다.
"""
import json
import re


def _last_tag(text: str, tag: str) -> str:
    """프롬프트의 입력 칸은 마지막 <tag>…</tag>에서 읽는다(본문이 같은 태그 이름을 먼저 언급한다)."""
    end = text.rfind(f"</{tag}>")
    start = text.rfind(f"<{tag}>", 0, end if end >= 0 else None)
    if start < 0 or end < 0:
        return ""
    return text[start + len(tag) + 2:end].strip()


def _pages(text: str) -> list:
    return [int(n) for n in re.findall(r"=== 페이지 (\d+) ===", _last_tag(text, "pages"))] or [1]


def _name(text: str) -> str:
    m = re.search(r'개념 "(.+?)"', text)
    return m.group(1) if m else "개념"


def _norm(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def answer(prompt_text: str) -> dict:
    head = prompt_text[:60]
    if "프롬프트 01" in head:
        from core import sample

        return sample.load_fixture("01")
    if "프롬프트 02" in head:
        from core import sample

        return sample.load_fixture("02")
    name, pages = _name(prompt_text), _pages(prompt_text)
    page = pages[len(pages) // 2]
    if "프롬프트 03-A" in head:
        fig = None
        target = "이 개념"
        if "순회" in name:
            fig = {"kind": "tree", "nodes": ["A", "B", "C", "D"], "caption": "예시 트리"}
            target = "아래 트리"
        elif "힙" in name:
            fig = {"kind": "array", "items": ["90", "75", "80"], "start": 1, "caption": "최대 힙 (인덱스 1부터)"}
            target = "아래 배열"
        return {
            "question": f"{target}에서 {name}의 과정을 쓰고, 그렇게 하는 이유를 쓰시오.",
            "answer": f"{name}은 자료에 나온 순서대로 한 단계씩 진행한다. 그렇게 하는 이유는 구조의 조건을 지키기 위해서다.",
            "rubric": [{"point": "과정을 순서대로 설명", "score": 4}, {"point": "이유 설명", "score": 3},
                       {"point": "용어를 정확히 사용", "score": 3}],
            "source_pages": [page], "figure": fig,
        }
    if "프롬프트 03-C" in head:
        return {
            "question": f"{name}에 대한 설명으로 옳은 것은?",
            "choices": [f"{name}은 자료의 정의를 그대로 따른다", f"{name}은 항상 배열의 끝에서 시작한다",
                        f"{name}은 형제 노드끼리 순서를 비교한다", f"{name}은 시간 복잡도가 O(n²)이다"],
            "answer_index": 0,
            "explanation": f"자료는 {name}의 정의를 설명한다(p.{page}). 형제끼리 비교한다는 설명은 자료에 없다.",
            "source_pages": [page], "figure": None,
        }
    if "프롬프트 03-B" in head:
        q = json.loads(_last_tag(prompt_text, "question"))
        given, model = _norm(_last_tag(prompt_text, "answer")), _norm(q["answer"])
        maxes = [r["score"] for r in q["rubric"]]
        if given == model:
            scores, error, reason = maxes, None, "과정과 이유를 모두 맞게 썼다."
        elif given and model.startswith(given):
            scores = maxes[:-1] + [0]
            error, reason = "절차 누락", f"과정은 맞지만 이유가 빠졌다 (p.{page})."
        else:
            scores = [1] + [0] * (len(maxes) - 1)
            error, reason = "개념 혼동", f"자료의 설명과 다른 개념을 썼다 (p.{page})."
        return {"score": sum(scores), "max": 10, "rubric_scores": scores, "status": "앎",
                "error_type": error, "reason": reason}
    if "프롬프트 04" in head:
        confusion = _last_tag(prompt_text, "student_confusion")
        reply = None
        if confusion and confusion != "(없음)":
            reply = f"두 보기는 비교하는 대상이 다르다. 자료는 {name}을 이렇게 설명한다(p.{page})."
        return {
            "my_gap": f"{name}의 핵심 절차를 정확히 쓰지 못했다.",
            "explanation": (f"{name}은 자료에서 '정의와 절차'로 설명한다(p.{page}).\n\n"
                            f"절차는 한 단계씩 진행하며 조건을 지킨다(p.{page}).\n\n"
                            "문제의 값에 그대로 적용하면 정답과 같은 결과가 나온다."),
            "check_pages": [page], "source_pages": [page],
            "not_found": False, "not_found_note": None, "confusion_reply": reply,
        }
    if "프롬프트 05" in head:
        detailed = "자세한 정도는 **자세히**" in prompt_text
        summary = f"{name}은 자료에서 정의와 함께 설명한다(p.{page})."
        if detailed:
            summary += f"\n\n절차는 한 단계씩 진행한다(p.{page}). 시간 복잡도도 함께 정리한다(p.{page})."
        return {
            "summary": summary,
            "key_points": [f"{name}의 정의", f"{name}의 절차 순서"] + (["시간 복잡도"] if detailed else []),
            "pitfalls": [f"{name}을 비슷한 연산과 혼동한다"] if detailed else [],
            "source_pages": [page],
        }
    return {}
