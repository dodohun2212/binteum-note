"""T-64: 녹음 받아쓰기. 가짜 OpenAI 클라이언트만 쓰고 실제로 부르지 않는다."""
import os
from types import SimpleNamespace

import pytest

from core import stt


class FakeClient:
    """client.audio.transcriptions.create(...)만 흉내 낸다."""

    def __init__(self, text="", error=None):
        self._text = text
        self._error = error
        self.calls = []
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        f = kwargs.get("file")
        self.calls.append({"model": kwargs.get("model"), "language": kwargs.get("language"),
                           "path": getattr(f, "name", ""), "data": f.read() if f else b""})
        if self._error:
            raise self._error
        return SimpleNamespace(text=self._text)


@pytest.fixture(autouse=True)
def _stt_on(monkeypatch):
    """config에서 음성 인식을 꺼 두어도 이 시험은 돌게 한다."""
    monkeypatch.setattr(stt, "STT_MODEL", "whisper-1")


# ---------- transcribe ----------

def test_t64_transcribe_success():
    client = FakeClient("오늘은 힙을 봅니다")
    assert stt.transcribe(b"audio-bytes", "a.m4a", client=client) == "오늘은 힙을 봅니다"
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["data"] == b"audio-bytes"
    assert call["language"] == "ko"
    assert call["path"].endswith(".m4a")
    # 임시 파일은 보낸 뒤 지워진다
    assert not os.path.exists(call["path"])


def test_t64_transcribe_error_becomes_stterror():
    client = FakeClient(error=RuntimeError("서버 오류"))
    with pytest.raises(stt.STTError) as info:
        stt.transcribe(b"audio-bytes", "a.m4a", client=client)
    assert info.value.code == "E-05"
    assert len(client.calls) == 1
    assert not os.path.exists(client.calls[0]["path"])


# ---------- resolve_transcript ----------

def test_t64_audio_only_source_is_audio():
    client = FakeClient("  오늘은 힙을 봅니다  ")
    out = stt.resolve_transcript(audio=b"..", audio_name="a.m4a", client=client)
    assert out == ("오늘은 힙을 봅니다", "audio", None)
    assert len(client.calls) == 1


@pytest.mark.parametrize("text", ["", "   \n "])
def test_t64_empty_transcript_gives_e05_notice(text):
    client = FakeClient(text)
    out = stt.resolve_transcript(audio=b"..", audio_name="a.m4a", client=client)
    assert out == (None, None, stt.E05)
    assert stt.E05 == stt.STTError.message
    assert "녹음 없이" in stt.E05


def test_t64_error_gives_notice_and_continues():
    client = FakeClient(error=RuntimeError("서버 오류"))
    text, source, notice = stt.resolve_transcript(audio=b"..", audio_name="a.m4a", client=client)
    assert text is None
    assert source is None
    assert notice == stt.E05


def test_t64_pasted_wins_and_client_not_called():
    client = FakeClient("녹음에서 나온 글")
    out = stt.resolve_transcript(pasted="  붙여넣은 대본  ", audio=b"..", audio_name="a.m4a", client=client)
    assert out == ("붙여넣은 대본", "paste", None)
    assert client.calls == []


def test_t64_nothing_given():
    client = FakeClient("쓰이지 않음")
    assert stt.resolve_transcript(client=client) == (None, None, None)
    assert stt.resolve_transcript(pasted="   ", audio=None, client=client) == (None, None, None)
    assert client.calls == []


def test_t64_phone_number_is_masked_in_audio_transcript():
    client = FakeClient("문의는 010-1234-5678로 주세요")
    text, source, notice = stt.resolve_transcript(audio=b"..", audio_name="a.m4a", client=client)
    assert source == "audio"
    assert notice is None
    assert "[마스킹]" in text
    assert "1234-5678" not in text


def test_t64_phone_number_is_masked_in_pasted_transcript():
    text, source, notice = stt.resolve_transcript(pasted="조교 번호는 010-1234-5678입니다")
    assert source == "paste"
    assert notice is None
    assert "[마스킹]" in text
    assert "1234-5678" not in text
