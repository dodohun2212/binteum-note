"""F03 녹음 → 대본 (OpenAI 전사 API). STT_MODEL이 None이면 쓰지 않는다."""
import os
import tempfile

from config import STT_MODEL
from core import llm
from core.extract import mask

E05 = "녹음을 글자로 바꾸지 못해 녹음 없이 계산했어요. 대본 붙여넣기로 다시 분석할 수 있어요"


class STTError(Exception):
    code = "E-05"
    message = E05

    def __str__(self):
        return self.message


def available() -> bool:
    return STT_MODEL is not None and bool(llm.get_key("OPENAI_API_KEY"))


def transcribe(data: bytes, name: str, client=None) -> str:
    """녹음 바이트 → 한국어 대본. 임시 파일은 보낸 직후 지운다."""
    if STT_MODEL is None:
        raise STTError()
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ".m4a"
    path = None
    try:
        if client is None:
            key = llm.get_key("OPENAI_API_KEY")
            if not key:
                raise STTError()
            from openai import OpenAI

            client = OpenAI(api_key=key, timeout=180)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            path = tmp.name
        with open(path, "rb") as f:
            result = client.audio.transcriptions.create(model=STT_MODEL, file=f, language="ko")
        return str(getattr(result, "text", "") or "")
    except STTError:
        raise
    except Exception as e:
        raise STTError() from e
    finally:
        if path and os.path.exists(path):
            os.remove(path)


def resolve_transcript(pasted: str = "", audio: bytes = None, audio_name: str = "", client=None) -> tuple:
    """(가린 대본 또는 None, 출처 "paste"/"audio"/None, 안내 문구 또는 None).

    붙여넣은 대본이 우선이다. 받아쓰기에 실패하면 녹음 없이 계속하고 E-05 안내를 돌려준다.
    """
    if pasted and pasted.strip():
        return mask(pasted.strip()), "paste", None
    if audio:
        try:
            text = transcribe(audio, audio_name, client=client).strip()
        except STTError:
            return None, None, E05
        if not text:
            return None, None, E05
        return mask(text), "audio", None
    return None, None, None
