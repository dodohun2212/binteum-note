"""F09 이해도 숫자화와 우선순위(8.5, 8.6). 외부 호출이 없는 순수 함수다."""
from config import AUTO_EXPLAIN_TOP

UNDERSTANDING = {"앎": 1.0, "헷갈림": 0.5, "모름": 0.0, "진단 안 함": 0.5}
NOT_DIAGNOSED = "진단 안 함"
ACTIONS = ("지금 당장", "다음", "복습만")


def action_of(priority: int) -> str:
    if priority >= 50:
        return "지금 당장"
    if priority >= 20:
        return "다음"
    return "복습만"


def compute_priorities(scores: list, grading: dict) -> list:
    """우선순위 = round(출제 점수 × (1 − 이해도)). 내림차순, 같으면 출제 점수 높은 순."""
    rows = []
    for r in scores:
        g = (grading or {}).get(r["concept_id"])
        status = g["status"] if g else NOT_DIAGNOSED
        understanding = UNDERSTANDING.get(status, 0.5)
        priority = round(r["pct"] * (1 - understanding))
        rows.append({"concept_id": r["concept_id"], "name": r["name"], "exam_pct": r["pct"],
                     "status": status, "understanding": understanding, "priority": priority,
                     "action": action_of(priority)})
    rows.sort(key=lambda x: (-x["priority"], -x["exam_pct"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def auto_explain_ids(priorities: list, confusion: dict = None) -> list:
    """자동으로 보완 설명을 만드는 개념: '지금 당장' 전부, 우선순위 상위 3개(0은 세지 않음),
    진단에서 모름·헷갈림이 나온 개념 전부, 헷갈린 점을 적은 개념."""
    confusion = confusion or {}
    top = [p["concept_id"] for p in priorities if p["priority"] > 0][:AUTO_EXPLAIN_TOP]
    out = []
    for p in priorities:
        cid = p["concept_id"]
        if (p["action"] == "지금 당장" or cid in top or p["status"] in ("모름", "헷갈림")
                or str(confusion.get(cid) or "").strip()):
            out.append(cid)
    return out


def split_review(items: list, confusion: dict = None) -> tuple:
    """'복습만' 묶음을 (펼쳐 둘 것, 접어 둘 것)으로 나눈다. 헷갈린 점을 적은 개념은 펼친다."""
    confusion = confusion or {}
    opened = [p for p in items if str(confusion.get(p["concept_id"]) or "").strip()]
    folded = [p for p in items if p not in opened]
    return opened, folded
