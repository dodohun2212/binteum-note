"""F11 샘플 자료와 저장해 둔 분석 결과(tests/fixtures). AI를 부르지 않는다."""
import json
from functools import lru_cache
from pathlib import Path

from core import concepts as concepts_mod
from core import score as score_mod
from core import utterances as utter_mod
from core.extract import extract, mask

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
FIXTURE_01 = ROOT / "tests" / "fixtures" / "01_개념추출_결과.json"
FIXTURE_02 = ROOT / "tests" / "fixtures" / "02_강조발화_결과.json"


def load_fixture(which: str) -> dict:
    path = FIXTURE_01 if which == "01" else FIXTURE_02
    return json.loads(path.read_text(encoding="utf-8"))


def load_sample() -> tuple:
    """(PDF 바이트, 가린 대본)."""
    return SAMPLE_PDF.read_bytes(), mask(SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"))


def saved_analysis(material: dict, transcript: str) -> dict:
    """저장된 호출 1·2 결과를 앱과 같은 검사에 통과시켜 점수까지 계산한다."""
    result = concepts_mod.clean_concepts(load_fixture("01"), material["n_pages"])
    meta = score_mod.find_meta_pages(material["pages"], result)
    utts = utter_mod.clean_utterances(load_fixture("02"), transcript, result["concepts"])
    scores = score_mod.compute_scores(result["concepts"], utts, meta)
    return {"concepts": result["concepts"], "meta_pages": meta, "utterances": utts, "scores": scores}


@lru_cache(maxsize=1)
def preview_top3() -> tuple:
    """첫 화면 '결과 미리보기'용: 저장된 결과로 코드가 계산한 상위 3개 (이름, 점수, 배지들)."""
    data, transcript = load_sample()
    material = extract(SAMPLE_PDF.name, data)
    scores = saved_analysis(material, transcript)["scores"]["scores"]
    return tuple((r["name"], r["pct"], tuple(score_mod.badges(r))) for r in scores[:3])
