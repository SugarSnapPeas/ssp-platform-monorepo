"""worker.jobs tests: the genuine api + shared-core edge for the worker lane."""

from datetime import date

import pytest

from api.catalog import seed_catalog
from api.orders import OrderBook
from api.pricing import LineItem
from shared_core.retry import RetryExhausted
from worker.jobs import JobResult, OrderProcessor, PaymentGateway, settle_payment
from worker.queue import Task, TaskQueue

DAY = date(2026, 8, 24)


def fixture_book(n=2):
    orders = OrderBook(seed_catalog())
    for i in range(n):
        orders.place(
            "buyer{0}@sugarsnap.example".format(i),
            [LineItem("SSP-1001", i + 1)],
            day=DAY,
        )
    return orders


def test_gateway_is_deterministic():
    gateway = PaymentGateway(flaky_for=2)
    with pytest.raises(ConnectionError):
        gateway.charge("ORD-1")
    with pytest.raises(ConnectionError):
        gateway.charge("ORD-1")
    assert gateway.charge("ORD-1") == "auth-ORD-1-3"


def test_settle_payment_retries_through_transient_failures():
    slept = []
    gateway = PaymentGateway(flaky_for=2)
    assert settle_payment(gateway, "ORD-1", attempts=3, sleeper=slept.append).startswith("auth-")
    assert gateway.calls == 3
    assert slept == [0.01, 0.02]  # shared_core.retry's backoff schedule


def test_settle_payment_gives_up_via_shared_core_retry():
    gateway = PaymentGateway(always_fail=True)
    with pytest.raises(RetryExhausted) as exc:
        settle_payment(gateway, "ORD-1", attempts=2, sleeper=lambda _: None)
    assert exc.value.attempts == 2
    assert isinstance(exc.value.__cause__, ConnectionError)


def test_enqueue_new_orders_queues_one_pay_task_each():
    orders = fixture_book(3)
    processor = OrderProcessor(orders)
    queue = processor.enqueue_new_orders(TaskQueue())
    tasks = queue.drain()
    assert [t.name for t in tasks] == ["pay", "pay", "pay"]
    assert [t.payload for t in tasks] == [
        "ORD-20260824-000001",
        "ORD-20260824-000002",
        "ORD-20260824-000003",
    ]


def test_processor_pays_and_advances_orders():
    orders = fixture_book(2)
    processor = OrderProcessor(orders)
    results = processor.run(processor.enqueue_new_orders(TaskQueue()))
    assert all(r.ok for r in results)
    assert orders.find_by_state("new") == []
    assert len(orders.find_by_state("paid")) == 2
    assert len(processor.authorisations) == 2


def test_processor_reports_payment_exhaustion_without_raising():
    orders = fixture_book(1)
    processor = OrderProcessor(orders, PaymentGateway(always_fail=True), attempts=2)
    results = processor.run(processor.enqueue_new_orders(TaskQueue()))
    assert results[0] == JobResult(
        "pay", "ORD-20260824-000001", False, "payment failed after 2"
    )
    assert orders.get("ORD-20260824-000001").state == "new"
    assert processor.failures() == results


def test_processor_surfaces_api_errors_as_failed_results():
    processor = OrderProcessor(fixture_book(1))
    queue = TaskQueue().push_many(
        [
            Task("pay", "ORD-20260824-000999"),   # NotFound
            Task("close", "ORD-20260824-000001"),  # illegal transition -> Conflict
        ]
    )
    results = processor.run(queue)
    assert [(r.ok, r.detail) for r in results] == [(False, "not_found"), (False, "conflict")]


def test_unknown_task_names_are_reported_not_raised():
    result = OrderProcessor(fixture_book(1)).handle(Task("dance", "ORD-1"))
    assert result == JobResult("dance", "ORD-1", False, "unknown task")


def test_full_lifecycle_through_the_processor():
    orders = fixture_book(1)
    processor = OrderProcessor(orders)
    order_id = "ORD-20260824-000001"
    processor.run(TaskQueue().push_many([Task("pay", order_id, priority=0)]))
    processor.run(TaskQueue().push_many([Task("fulfil", order_id), Task("close", order_id)]))
    assert orders.get(order_id).state == "closed"
    assert orders.get(order_id).history == ["new", "paid", "fulfilled", "closed"]
    assert processor.failures() == []
