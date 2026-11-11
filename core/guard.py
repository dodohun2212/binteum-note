"""F14 API 비용 보호: 세션·하루 분석 횟수, 하루 AI 호출 수, 샘플 결과 재사용.

streamlit에 기대지 않는다. 화면 쪽 연결은 screens/common.py가 한다.
"""
import copy
import threading
from collections import OrderedDict

from core.html import kst_today


def session_left(used: int, limit: int) -> int:
    """이 세션에서 더 할 수 있는 분석 횟수. limit이 0 이하면 제한 없음(-1)."""
    if limit <= 0:
        return -1
    return max(0, limit - max(0, used))


def refund_needed(failed: bool, ai_calls: int) -> tuple:
    """분석 횟수를 돌려줄지 (세션, 하루).

    AI를 부르기 전에 실패하면 둘 다 돌려준다. 성공했지만 저장된 결과만 써서
    AI 호출이 0번이면 하루 횟수만 돌려준다. 그 밖에는 돌려주지 않는다.
    """
    if ai_calls > 0:
        return (False, False)
    if failed:
        return (True, True)
    return (False, True)


def needs_reload(previous, now: dict) -> bool:
    """재배포 뒤 예전 모듈·캐시를 버릴지. 기록은 {"modules": {파일: 시각}, "prompts": {파일: 시각}}.

    모듈 시각이 바뀌었거나, 프롬프트 시각이 바뀌었거나 지난 기록에 없으면 버린다.
    """
    if not previous:
        return True
    if "prompts" not in previous or previous.get("prompts") != now.get("prompts"):
        return True
    return previous.get("modules") != now.get("modules")


class DailyCounter:
    """서버 전체 하루 횟수. 날짜(한국 시간)가 바뀌면 0부터. limit 0은 제한 없음."""

    def __init__(self, limit: int, today=None):
        self.limit = limit
        self._today = today or kst_today
        self._day = self._today()
        self._count = 0
        self._lock = threading.Lock()

    def _roll(self):
        day = self._today()
        if day != self._day:
            self._day = day
            self._count = 0

    @property
    def count(self) -> int:
        with self._lock:
            self._roll()
            return self._count

    @property
    def full(self) -> bool:
        """상한에 닿았는지. 닿았으면 새 작업을 시작하지 않는다."""
        with self._lock:
            self._roll()
            return self.limit > 0 and self._count >= self.limit

    def try_take(self) -> bool:
        with self._lock:
            self._roll()
            if self.limit > 0 and self._count >= self.limit:
                return False
            self._count += 1
            return True

    def give_back(self) -> None:
        with self._lock:
            self._roll()
            if self._count > 0:
                self._count -= 1

    def add(self, n: int) -> None:
        """실제로 쓴 횟수를 더한다(하루 AI 호출 수)."""
        if n <= 0:
            return
        with self._lock:
            self._roll()
            self._count += n


class ResultCache:
    """서버에 하나 두는 결과 저장소. 넘치면 오래된 것부터 버린다. 꺼낼 때는 복사본."""

    def __init__(self, max_items: int = 200):
        self.max_items = max_items
        self._items = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._items:
                return None
            return copy.deepcopy(self._items[key])

    def put(self, key, value) -> None:
        with self._lock:
            if key in self._items:
                self._items.pop(key)
            self._items[key] = copy.deepcopy(value)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
