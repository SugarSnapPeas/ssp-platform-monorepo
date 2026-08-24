"""A small, deterministic retry decorator.

``time.sleep`` is injectable so the behaviour is fully testable without the
tests actually sleeping.
"""

from __future__ import annotations

import functools
import time
from typing import Callable, List, Optional, Sequence, Tuple, Type

__all__ = ["RetryExhausted", "backoff_delays", "retry"]


class RetryExhausted(RuntimeError):
    """Raised when every attempt failed. ``__cause__`` is the last error."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        super().__init__(
            "gave up after {0} attempt(s): {1!r}".format(attempts, last_error)
        )
        self.attempts = attempts
        self.last_error = last_error


def backoff_delays(
    attempts: int,
    delay: float = 0.1,
    factor: float = 2.0,
    max_delay: Optional[float] = None,
) -> List[float]:
    """Return the sleep intervals between ``attempts`` tries.

    There is always one fewer delay than there are attempts.

    >>> backoff_delays(4, delay=1.0, factor=2.0)
    [1.0, 2.0, 4.0]
    >>> backoff_delays(4, delay=1.0, factor=2.0, max_delay=3.0)
    [1.0, 2.0, 3.0]
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if delay < 0:
        raise ValueError("delay must not be negative")
    if factor < 1:
        raise ValueError("factor must be >= 1")
    out: List[float] = []
    current = float(delay)
    for _ in range(attempts - 1):
        if max_delay is not None:
            current = min(current, float(max_delay))
        out.append(current)
        current = current * factor
    return out


def retry(
    attempts: int = 3,
    delay: float = 0.1,
    factor: float = 2.0,
    max_delay: Optional[float] = None,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    sleeper: Callable[[float], None] = time.sleep,
    on_retry: Optional[Callable[[int, BaseException], None]] = None,
):
    """Retry the wrapped callable on ``exceptions`` with exponential backoff.

    The wrapper exposes ``.call_count`` so callers can assert on effort, and
    raises :class:`RetryExhausted` (chained from the final error) when every
    attempt fails.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if not isinstance(exceptions, tuple) or not exceptions:
        raise TypeError("exceptions must be a non-empty tuple of exception types")

    schedule = backoff_delays(attempts, delay=delay, factor=factor, max_delay=max_delay)

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error: Optional[BaseException] = None
            for attempt in range(1, attempts + 1):
                wrapper.call_count += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc
                    if attempt == attempts:
                        break
                    if on_retry is not None:
                        on_retry(attempt, exc)
                    sleeper(schedule[attempt - 1])
            assert last_error is not None
            raise RetryExhausted(attempts, last_error) from last_error

        wrapper.call_count = 0
        wrapper.retry_attempts = attempts
        wrapper.retry_schedule = list(schedule)
        return wrapper

    return decorator
