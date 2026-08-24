"""Pure worker tests: no api, no shared-core. The worker lane's control case."""

import pytest

from worker.queue import QueueEmpty, Task, TaskQueue


def test_task_validation():
    assert Task("pay", "ORD-1").priority == 5
    for bad_name in ("", "   ", None, 7):
        with pytest.raises((ValueError, TypeError)):
            Task(bad_name, "x")
    with pytest.raises(TypeError):
        Task("pay", "x", priority=True)
    with pytest.raises(ValueError):
        Task("pay", "x", priority=10)


def test_priority_order_then_fifo():
    queue = TaskQueue().push_many(
        [
            Task("c", 3, priority=5),
            Task("a", 1, priority=1),
            Task("d", 4, priority=5),
            Task("b", 2, priority=1),
        ]
    )
    assert [t.name for t in queue.drain()] == ["a", "b", "c", "d"]


def test_len_bool_and_peek():
    queue = TaskQueue()
    assert len(queue) == 0 and not queue
    queue.push(Task("pay", "ORD-1"))
    assert len(queue) == 1 and queue
    assert queue.peek().name == "pay"
    assert len(queue) == 1  # peek does not consume


def test_pop_and_peek_on_empty_queue():
    queue = TaskQueue()
    with pytest.raises(QueueEmpty):
        queue.pop()
    with pytest.raises(QueueEmpty):
        queue.peek()


def test_push_rejects_non_tasks():
    with pytest.raises(TypeError):
        TaskQueue().push("pay")


def test_drain_respects_limit():
    queue = TaskQueue().push_many([Task("t{0}".format(i), i) for i in range(5)])
    assert len(queue.drain(2)) == 2
    assert len(queue) == 3
    assert len(queue.drain()) == 3
    assert queue.drain() == []


def test_drain_limit_validation():
    queue = TaskQueue()
    with pytest.raises(TypeError):
        queue.drain(True)
    with pytest.raises(ValueError):
        queue.drain(-1)


def test_iteration_drains_in_execution_order():
    queue = TaskQueue().push_many(
        [Task("low", 1, priority=9), Task("high", 2, priority=0)]
    )
    assert [t.name for t in queue] == ["high", "low"]
    assert len(queue) == 0
