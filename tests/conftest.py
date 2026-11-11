"""테스트 공통 준비. AI를 부르지 않게 가짜 AI 모드를 켠다."""
import os
import sys
import warnings
from pathlib import Path

os.environ["BINTM_FAKE_AI"] = "1"
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", category=DeprecationWarning)

import pytest  # noqa: E402

from core import extract, sample  # noqa: E402


@pytest.fixture(scope="session")
def sample_bytes():
    """샘플 PDF 바이트."""
    return sample.SAMPLE_PDF.read_bytes()


@pytest.fixture(scope="session")
def material(sample_bytes):
    """샘플 PDF에서 뽑은 material(20쪽)."""
    return extract.extract(sample.SAMPLE_PDF.name, sample_bytes)


@pytest.fixture(scope="session")
def transcript():
    """가린 샘플 대본."""
    return sample.load_sample()[1]


@pytest.fixture(scope="session")
def analysis(material, transcript):
    """저장된 호출 1·2 결과로 계산한 개념·발화·점수."""
    return sample.saved_analysis(material, transcript)
