"""A tiny deterministic priority queue.

Pure worker code: imports neither ``api`` nor ``shared_core``. This is the
control module for the worker lane — a change to shared-core or to api must
not select ``tests/test_queue.py``.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Tuple

__all__ = ["QueueEmpty", "Task", "TaskQueue"]


class QueueEmpty(LookupError):
    """Raised by :meth:`TaskQueue.pop` when there is nothing to do."""


@dataclass(frozen=True)
class Task:
    name: str
    payload: Any
    priority: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("task name must be a non-empty string")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be an int")
        if not 0 <= self.priority <= 9:
            raise ValueError("priority must be between 0 (highest) and 9 (lowest)")


class TaskQueue:
    """Lowest ``priority`` value first; FIFO within a priority."""

    def __init__(self) -> None:
        self._heap: List[Tuple[int, int, Task]] = []
        self._counter = itertools.count()

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    def __iter__(self) -> Iterator[Task]:
        """Drain the queue in execution order."""
        while self._heap:
            yield self.pop()

    def push(self, task: Task) -> "TaskQueue":
        if not isinstance(task, Task):
            raise TypeError("expected a Task")
        heapq.heappush(self._heap, (task.priority, next(self._counter), task))
        return self

    def push_many(self, tasks) -> "TaskQueue":
        for task in tasks:
            self.push(task)
        return self

    def peek(self) -> Task:
        if not self._heap:
            raise QueueEmpty("queue is empty")
        return self._heap[0][2]

    def pop(self) -> Task:
        if not self._heap:
            raise QueueEmpty("queue is empty")
        return heapq.heappop(self._heap)[2]

    def drain(self, limit: Optional[int] = None) -> List[Task]:
        """Pop up to ``limit`` tasks (all of them when ``limit`` is ``None``)."""
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int)):
            raise TypeError("limit must be an int or None")
        if limit is not None and limit < 0:
            raise ValueError("limit must not be negative")
        out: List[Task] = []
        while self._heap and (limit is None or len(out) < limit):
            out.append(self.pop())
        return out
