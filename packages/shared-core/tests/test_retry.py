import pytest

from shared_core.retry import RetryExhausted, backoff_delays, retry


def test_backoff_delays_grow_geometrically():
    assert backoff_delays(4, delay=1.0, factor=2.0) == [1.0, 2.0, 4.0]
    assert backoff_delays(1, delay=1.0) == []


def test_backoff_delays_respect_max_delay():
    assert backoff_delays(5, delay=1.0, factor=3.0, max_delay=4.0) == [1.0, 3.0, 4.0, 4.0]


@pytest.mark.parametrize(
    "kwargs", [{"attempts": 0}, {"attempts": 3, "delay": -1}, {"attempts": 3, "factor": 0.5}]
)
def test_backoff_delays_validation(kwargs):
    with pytest.raises(ValueError):
        backoff_delays(**kwargs)


def test_succeeds_first_time_without_sleeping():
    slept = []

    @retry(attempts=3, sleeper=slept.append)
    def ok():
        return "fine"

    assert ok() == "fine"
    assert ok.call_count == 1
    assert slept == []


def test_retries_until_success_and_sleeps_on_the_schedule():
    slept = []
    state = {"n": 0}

    @retry(attempts=4, delay=0.5, factor=2.0, sleeper=slept.append)
    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise IOError("transient")
        return state["n"]

    assert flaky() == 3
    assert flaky.call_count == 3
    assert slept == [0.5, 1.0]


def test_exhaustion_raises_and_chains_the_last_error():
    slept = []

    @retry(attempts=3, delay=0.1, sleeper=slept.append)
    def always_bad():
        raise KeyError("nope")

    with pytest.raises(RetryExhausted) as exc:
        always_bad()
    assert exc.value.attempts == 3
    assert isinstance(exc.value.__cause__, KeyError)
    assert always_bad.call_count == 3
    assert len(slept) == 2


def test_unlisted_exceptions_propagate_immediately():
    slept = []

    @retry(attempts=5, exceptions=(ValueError,), sleeper=slept.append)
    def wrong_error():
        raise TypeError("not retryable")

    with pytest.raises(TypeError):
        wrong_error()
    assert wrong_error.call_count == 1
    assert slept == []


def test_on_retry_hook_observes_each_failure():
    seen = []

    @retry(attempts=3, sleeper=lambda _: None, on_retry=lambda n, e: seen.append((n, str(e))))
    def bad():
        raise RuntimeError("boom")

    with pytest.raises(RetryExhausted):
        bad()
    assert seen == [(1, "boom"), (2, "boom")]


def test_decorator_preserves_metadata_and_exposes_schedule():
    @retry(attempts=3, delay=1.0, factor=2.0, sleeper=lambda _: None)
    def documented(a, b=2):
        """docstring survives"""
        return a + b

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "docstring survives"
    assert documented.retry_schedule == [1.0, 2.0]
    assert documented(1, b=5) == 6


def test_decorator_argument_validation():
    with pytest.raises(ValueError):
        retry(attempts=0)
    with pytest.raises(TypeError):
        retry(exceptions=ValueError)
    with pytest.raises(TypeError):
        retry(exceptions=())
