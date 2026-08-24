"""In-process end-to-end worker test across queue + jobs + settlement + reporting.

Always selected via ``test-selection-rules`` in
``services/worker/.circleci/test-suites.yml``.
"""

from datetime import date

from api.catalog import seed_catalog
from api.orders import OrderBook
from api.pricing import LineItem
from shared_core.money import Money, total
from worker.jobs import OrderProcessor, PaymentGateway
from worker.queue import Task, TaskQueue
from worker.reporting import bucket_by
from worker.settlement import settle

DAY = date(2026, 8, 24)


def test_queue_to_settlement_to_report():
    orders = OrderBook(seed_catalog())
    orders.place("a@sugarsnap.example", [LineItem("SSP-1001", 4)], day=DAY)   # 14.00
    orders.place("b@sugarsnap.example", [LineItem("SSP-2001", 2)], day=DAY)   # 37.98

    # 1. drive both orders to fulfilled through the queue
    processor = OrderProcessor(orders, PaymentGateway(flaky_for=1))
    assert all(r.ok for r in processor.run(processor.enqueue_new_orders(TaskQueue())))

    fulfil_queue = TaskQueue().push_many(
        [Task("fulfil", o.order_id) for o in orders.find_by_state("paid")]
    )
    assert all(r.ok for r in processor.run(fulfil_queue))
    assert len(orders.find_by_state("fulfilled")) == 2
    assert orders.outstanding_total().is_zero()

    # 2. settle each one, checking nothing is lost
    runs = [settle(o.priced, {"merchant": 7, "grower": 3}) for o in orders.find_by_state("fulfilled")]
    assert all(r.balances() for r in runs)

    # 3. report on the payouts
    rows = [(p.party, p.amount) for run in runs for p in run.payouts]
    buckets = bucket_by(rows, "USD")
    assert [b.key for b in buckets] == ["merchant", "grower"]
    assert total([b.amount for b in buckets], "USD") == total(
        [r.net for r in runs], "USD"
    )


def test_gateway_flakiness_is_absorbed_end_to_end():
    orders = OrderBook(seed_catalog())
    orders.place("a@sugarsnap.example", [LineItem("SSP-1002", 1)], day=DAY)
    processor = OrderProcessor(orders, PaymentGateway(flaky_for=2), attempts=3)
    results = processor.run(processor.enqueue_new_orders(TaskQueue()))
    assert [r.ok for r in results] == [True]
    assert processor.gateway.calls == 3
    assert processor.failures() == []


def test_totals_survive_the_whole_pipeline():
    orders = OrderBook(seed_catalog())
    placed = orders.place("a@sugarsnap.example", [LineItem("SSP-1001", 7)], day=DAY)
    assert placed.total == Money.of("24.50", "USD")
    run = settle(placed.priced, {"merchant": 1, "grower": 1})
    assert run.fee + total([p.amount for p in run.payouts], "USD") == Money.of("24.50", "USD")
