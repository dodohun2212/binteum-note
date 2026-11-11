"""기출 비교(개발기획안 8.7): 출제 점수 상위 N개 중 실제 출제 개념이 몇 개인지 센다.

    python scripts/compare_exam.py --material 자료.pdf --exam tests/기출_개념표.json [--transcript 대본.txt] [--top 10]

기출_개념표.json 모양: {"concepts": ["힙의 삽입 연산", "이진 트리의 순회"]} (문제 원문은 넣지 않는다)
개념 추출에 실제 AI를 쓴다(환경변수 또는 .streamlit/secrets.toml의 키). 결과 숫자는 그대로 README에 적는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import concepts, extract, llm, score, utterances  # noqa: E402
from scripts.make_example import load_key  # noqa: E402


def _norm(s: str) -> str:
    return re.sub(r"[\s·,()]+", "", str(s)).lower()


def matches(name: str, exam_names: list) -> bool:
    """이름이 같거나 한쪽이 다른 쪽을 포함하면 같은 개념으로 본다(사람이 한 번 더 확인할 것)."""
    a = _norm(name)
    return any(a == _norm(e) or a in _norm(e) or _norm(e) in a for e in exam_names)


def count_hits(scores: list, exam_names: list, top: int = 10) -> tuple:
    rows = scores[:top]
    hit = [r["name"] for r in rows if matches(r["name"], exam_names)]
    return len(hit), len(rows), hit


def main() -> None:
    parser = argparse.ArgumentParser(description="기출 비교")
    parser.add_argument("--material", required=True)
    parser.add_argument("--exam", required=True)
    parser.add_argument("--transcript")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    load_key()
    if not llm.has_key():
        print("키가 없어요.")
        sys.exit(1)
    path = Path(args.material)
    material = extract.extract(path.name, path.read_bytes())
    transcript = extract.mask(Path(args.transcript).read_text(encoding="utf-8")) if args.transcript else ""
    usage = llm.Usage()
    result = concepts.extract_concepts(material, usage)
    utts = utterances.find_utterances(transcript, result["concepts"], usage)
    meta = score.find_meta_pages(material["pages"], result)
    rows = score.compute_scores(result["concepts"], utts, meta)["scores"]
    exam = json.loads(Path(args.exam).read_text(encoding="utf-8"))["concepts"]
    hit, total, names = count_hits(rows, exam, args.top)
    print(f"상위 {total}개 중 실제 출제 개념 {hit}개: {names}")
    print(f"AI 호출 {usage.calls}번, 입력 {usage.input_tokens} · 출력 {usage.output_tokens} 토큰")


if __name__ == "__main__":
    main()
