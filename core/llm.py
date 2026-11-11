"""모든 언어 모델 호출이 거치는 곳. 앱의 다른 코드는 ask_json()만 부른다."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from config import AI_MAX_TOKENS, LLM_MODEL

# 모든 호출에 붙는 시스템 지시 한 줄 (BR-10의 예외)
SYSTEM = "출력은 JSON 객체 하나만 씁니다. 설명 문장이나 코드 블록 표시(```)를 붙이지 않습니다."
MAX_TOKENS_CAP = 16000
RETRY_WAITS = (2, 4)   # 네트워크·429·5xx: 2초 → 4초 기다리고 최대 2회 더
TIMEOUT = 90           # 호출 하나가 이 시간을 넘기면 실패


class LLMError(Exception):
    code = "E-07"
    message = "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요"

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.message)
        self.detail = detail


class NoKeyError(LLMError):
    code = "E-06"
    message = "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요"


class APIError(LLMError):
    code = "E-07"


class BadJSONError(LLMError):
    code = "E-08"
    message = "AI 답을 읽지 못했어요. 다시 시도해 주세요"


class LimitError(LLMError):
    code = "E-17"
    message = ("오늘 이 앱에서 쓸 수 있는 분석 횟수를 다 썼어요. 내일 다시 이용해 주세요. "
               "직접 실행하려면 README의 로컬 실행 방법을 보세요.")


def error_text(exc: Exception) -> tuple:
    """예외 → (화면 문구, 에러 코드). 기술 메시지는 따로 펼침 상자에만 보인다."""
    if isinstance(exc, LLMError):
        return exc.message, exc.code
    code = getattr(exc, "code", "")
    message = getattr(exc, "message", "")
    if code and message:
        return message, code
    return "알 수 없는 오류가 났어요. 처음부터 다시 해 주세요", ""


@dataclass
class Usage:
    """AI 호출 수와 토큰. 스레드마다 하나씩 쓰고 끝난 뒤 합친다."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, seconds: float = 0.0) -> None:
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.seconds += float(seconds or 0.0)

    def merge(self, other: "Usage") -> None:
        """묶음을 더한다. 호출 수도 묶음 안의 호출 수만큼 는다."""
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds


_keys = {}


def configure(anthropic_key=None, openai_key=None) -> None:
    """화면 쪽(st.secrets)이나 스크립트가 읽은 키를 넘겨 둔다. 없으면 환경변수를 본다."""
    _keys["ANTHROPIC_API_KEY"] = anthropic_key or None
    _keys["OPENAI_API_KEY"] = openai_key or None


def get_key(name: str):
    return _keys.get(name) or os.environ.get(name) or None


def is_fake() -> bool:
    return os.environ.get("BINTM_FAKE_AI") == "1"


def has_key() -> bool:
    return is_fake() or bool(get_key("ANTHROPIC_API_KEY"))


def extract_json(text: str) -> dict:
    """답에 글이 섞여도 첫 '{'부터 마지막 '}'까지만 잘라 읽는다."""
    start, end = (text or "").find("{"), (text or "").rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 객체가 없음")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    return data


def _call_model(prompt_text: str, max_tokens: int, thinking: bool) -> tuple:
    """실제 호출 한 번 → (답 글, stop_reason, 입력 토큰, 출력 토큰)."""
    if is_fake():
        from core import fake_ai

        text = json.dumps(fake_ai.answer(prompt_text), ensure_ascii=False)
        return text, "end_turn", len(prompt_text) // 3, len(text) // 3
    key = get_key("ANTHROPIC_API_KEY")
    if not key:
        raise NoKeyError()
    import anthropic

    client = anthropic.Anthropic(api_key=key, timeout=TIMEOUT, max_retries=0)
    kwargs = {"model": LLM_MODEL, "max_tokens": max_tokens, "system": SYSTEM,
              "messages": [{"role": "user", "content": prompt_text}]}
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    last = None
    for wait in (0,) + RETRY_WAITS:
        if wait:
            time.sleep(wait)
        try:
            with client.messages.stream(**kwargs) as stream:
                msg = stream.get_final_message()
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return text, msg.stop_reason, msg.usage.input_tokens, msg.usage.output_tokens
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise NoKeyError(type(e).__name__) from e
        except anthropic.RateLimitError as e:
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code < 500:
                raise APIError(f"{type(e).__name__} {e.status_code}") from e
            last = e
        except anthropic.APIConnectionError as e:  # 시간 초과 포함
            last = e
    raise APIError(type(last).__name__)


def ask_json(prompt_text: str, max_tokens: int = AI_MAX_TOKENS, thinking: bool = False, usage=None) -> dict:
    """프롬프트 → JSON(dict). 읽지 못하면 같은 요청을 한 번 더, 또 실패하면 BadJSONError(E-08).

    답이 상한에 걸려 잘렸으면 상한을 두 배로(최대 16000) 늘려 다시 받는다.
    """
    tokens = max_tokens
    last_text = ""
    for _ in range(2):
        started = time.time()
        text, stop_reason, n_in, n_out = _call_model(prompt_text, tokens, thinking)
        if usage is not None:
            usage.add(n_in, n_out, time.time() - started)
        try:
            return extract_json(text)
        except ValueError:
            last_text = text or ""
            if stop_reason == "max_tokens":
                tokens = min(tokens * 2, MAX_TOKENS_CAP)
    raise BadJSONError(last_text[:400])


def run_many(jobs: dict, workers: int = 6, on_done=None) -> tuple:
    """개념별 호출을 동시에 부른다. jobs = {키: fn(usage)}.

    돌려주는 값은 (결과 {키: 값}, 실패 {키: 예외}, 합친 Usage). 하나가 실패해도 나머지는 살린다.
    on_done(끝난 수, 전체 수)는 이 함수를 부른 스레드에서 불린다(진행 막대용).
    """
    results, errors, total = {}, {}, Usage()
    if not jobs:
        return results, errors, total
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {}
        for key, fn in jobs.items():
            usage = Usage()
            futures[pool.submit(fn, usage)] = (key, usage)
        for n, fut in enumerate(as_completed(futures), 1):
            key, usage = futures[fut]
            total.merge(usage)
            try:
                results[key] = fut.result()
            except Exception as e:  # 개념마다 따로 잡는다
                errors[key] = e
            if on_done:
                on_done(n, len(futures))
    ordered = {k: results[k] for k in jobs if k in results}
    return ordered, errors, total
