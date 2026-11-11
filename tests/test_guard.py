"""T-35~T-39, T-59 일부: 비용 보호(횟수·저장소), 빠른 진단 대상, 호출 수 세기."""
import threading
from datetime import date

import pytest

import config
from core import diagnose, guard, llm


# ---------- T-35 세션 분석 횟수 ----------

@pytest.mark.parametrize("used, left", [(0, 5), (4, 1), (5, 0), (9, 0)])
def test_t35_session_left(used, left):
    assert guard.session_left(used, 5) == left


def test_t35_session_no_limit():
    assert guard.session_left(0, 0) == -1
    assert guard.session_left(99, 0) == -1


def test_t35_config_values():
    assert config.MAX_ANALYSES_PER_SESSION > 0
    assert config.MAX_ANALYSES_PER_DAY >= config.MAX_ANALYSES_PER_SESSION
    assert config.QUICK_DIAG_TOP > 0


# ---------- T-36 하루 분석 횟수 ----------

def test_t36_daily_limit_three():
    counter = guard.DailyCounter(limit=3)
    assert [counter.try_take() for _ in range(4)] == [True, True, True, False]
    assert counter.count == 3


def test_t36_give_back_allows_one_more():
    counter = guard.DailyCounter(limit=3)
    for _ in range(3):
        counter.try_take()
    assert counter.try_take() is False
    counter.give_back()
    assert counter.count == 2
    assert counter.try_take() is True
    assert counter.try_take() is False
    assert counter.count == 3


def test_t36_new_day_starts_from_zero():
    day = {"now": date(2026, 11, 10)}
    counter = guard.DailyCounter(limit=3, today=lambda: day["now"])
    assert [counter.try_take() for _ in range(4)] == [True, True, True, False]
    day["now"] = date(2026, 11, 11)
    assert counter.count == 0
    assert counter.try_take() is True
    assert counter.count == 1


def test_t36_limit_zero_always_allows():
    counter = guard.DailyCounter(limit=0)
    assert all(counter.try_take() for _ in range(50))
    assert counter.count == 50


def test_t36_threads_take_exactly_limit():
    counter = guard.DailyCounter(limit=100)
    allowed = []
    start = threading.Barrier(8)

    def work():
        start.wait()
        got = sum(1 for _ in range(50) if counter.try_take())
        allowed.append(got)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(allowed) == 8
    assert sum(allowed) == 100
    assert counter.count == 100


# ---------- T-37 결과 재사용 ----------

def test_t37_cache_drops_only_oldest():
    cache = guard.ResultCache(max_items=2)
    cache.put("a", {"v": 1})
    cache.put("b", {"v": 2})
    cache.put("c", {"v": 3})
    assert len(cache) == 2
    assert cache.get("a") is None
    assert cache.get("b") == {"v": 2}
    assert cache.get("c") == {"v": 3}


def test_t37_cache_returns_copy():
    cache = guard.ResultCache(max_items=2)
    cache.put("a", {"items": [1, 2]})
    got = cache.get("a")
    got["items"].append(3)
    got["new"] = True
    assert cache.get("a") == {"items": [1, 2]}


def test_t37_cache_stores_copy():
    cache = guard.ResultCache(max_items=2)
    value = {"items": [1, 2]}
    cache.put("a", value)
    value["items"].append(3)
    assert cache.get("a") == {"items": [1, 2]}


def test_t37_empty_cache_is_not_none():
    cache = guard.ResultCache(max_items=2)
    assert len(cache) == 0
    assert cache is not None
    assert cache.get("없는 키") is None


# ---------- T-38 빠른 진단 대상 ----------

PCTS = [100, 98, 96, 66, 65, 46, 35, 32, 31, 20, 19, 8, 0]  # 20점 이상 10개


def _scores():
    return [{"concept_id": f"c{i}", "name": f"개념{i}", "pct": pct} for i, pct in enumerate(PCTS, 1)]


def test_t38_all_targets_over_min():
    expected = [f"c{i}" for i in range(1, 11)]
    assert diagnose.diag_targets(_scores()) == expected
    assert diagnose.diag_targets(_scores(), top=None) == expected


def test_t38_top5_in_rank_order():
    assert diagnose.diag_targets(_scores(), top=5) == ["c1", "c2", "c3", "c4", "c5"]


def test_t38_top50_is_all_ten():
    assert diagnose.diag_targets(_scores(), top=50) == [f"c{i}" for i in range(1, 11)]


# ---------- T-39 호출 수 세기 ----------

def test_t39_usage_merge_counts_calls_in_bundle():
    bundle = llm.Usage()
    bundle.add(100, 50)
    bundle.add(110, 40)
    total = llm.Usage()
    total.merge(bundle)
    total.add(100, 35)
    assert total.calls == 3
    assert total.input_tokens == 310
    assert total.output_tokens == 125


def test_t39_run_many_keeps_good_results():
    def ok(value):
        def job(usage):
            usage.add(10, 5)
            return value
        return job

    def bad(usage):
        usage.add(10, 5)
        raise RuntimeError("가짜 실패")

    seen = []
    results, errors, total = llm.run_many(
        {"a": ok("가"), "b": bad, "c": ok("다")}, workers=3,
        on_done=lambda done, n: seen.append((done, n)))
    assert results == {"a": "가", "c": "다"}
    assert list(errors) == ["b"]
    assert isinstance(errors["b"], RuntimeError)
    assert len(seen) == 3
    assert sorted(seen) == [(1, 3), (2, 3), (3, 3)]
    assert total.calls == 3
    assert total.input_tokens == 30
    assert total.output_tokens == 15


def test_t39_run_many_empty():
    results, errors, total = llm.run_many({})
    assert results == {}
    assert errors == {}
    assert total.calls == 0


# ---------- T-59 일부: 돌려주기와 하루 AI 호출 상한 ----------

@pytest.mark.parametrize("failed, ai_calls, expected", [
    (True, 0, (True, True)),      # AI 호출 전 실패: 둘 다 돌려줌
    (False, 0, (False, True)),    # 저장된 결과만 씀: 하루 횟수만 돌려줌
    (True, 3, (False, False)),    # AI 호출 뒤 실패: 돌려주지 않음
    (False, 2, (False, False)),   # 보통 성공
])
def test_t59_refund_needed(failed, ai_calls, expected):
    assert guard.refund_needed(failed, ai_calls) == expected


def test_t59_full_after_reaching_limit():
    counter = guard.DailyCounter(limit=5)
    assert counter.full is False
    counter.add(4)
    assert counter.full is False
    counter.add(1)
    assert counter.count == 5
    assert counter.full is True


def test_t59_full_never_true_without_limit():
    counter = guard.DailyCounter(limit=0)
    counter.add(5)
    counter.add(10_000)
    assert counter.full is False
