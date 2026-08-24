"""api.orders tests — exercise shared-core ids + validation in-process."""

from datetime import date
from decimal import Decimal

import pytest

from api.catalog import seed_catalog
from api.errors import Conflict, NotFound
from api.orders import Order, OrderBook
from api.pricing import LineItem
from shared_core.money import Money
from shared_core.validation import ValidationError

DAY = date(2026, 8, 24)


def book():
    return OrderBook(seed_catalog())


def test_place_assigns_sequential_ids():
    orders = book()
    first = orders.place("peas@sugarsnap.example", [LineItem("SSP-1001", 1)], day=DAY)
    second = orders.place("pods@sugarsnap.example", [LineItem("SSP-1002", 1)], day=DAY)
    assert first.order_id == "ORD-20260824-000001"
    assert second.order_id == "ORD-20260824-000002"
    assert len(orders) == 2
    assert first.placed_on == DAY


def test_place_validates_and_normalises_the_customer_email():
    orders = book()
    placed = orders.place("  Peas@SugarSnap.EXAMPLE ", [LineItem("SSP-1001", 1)], day=DAY)
    assert placed.customer_email == "Peas@sugarsnap.example"
    with pytest.raises(ValidationError):
        orders.place("not-an-email", [LineItem("SSP-1001", 1)], day=DAY)


def test_place_prices_the_basket():
    orders = book()
    placed = orders.place(
        "peas@sugarsnap.example",
        [LineItem("SSP-1001", 10)],
        tax_rate=Decimal("0.10"),
        promo="PODSQUAD",
        day=DAY,
    )
    assert placed.priced.line_discount == Money.of("1.75", "USD")
    assert placed.total == Money.of("34.75", "USD")


def test_happy_path_state_machine():
    orders = book()
    placed = orders.place("peas@sugarsnap.example", [LineItem("SSP-1001", 1)], day=DAY)
    orders.advance(placed.order_id, "paid")
    orders.advance(placed.order_id, "fulfilled")
    final = orders.advance(placed.order_id, "closed")
    assert final.state == "closed"
    assert final.history == ["new", "paid", "fulfilled", "closed"]
    assert final.is_terminal()


@pytest.mark.parametrize("target", ["fulfilled", "closed", "refunded"])
def test_illegal_transitions_from_new(target):
    orders = book()
    placed = orders.place("peas@sugarsnap.example", [LineItem("SSP-1001", 1)], day=DAY)
    with pytest.raises(Conflict):
        placed.transition_to(target)
    assert placed.state == "new"


def test_unknown_state_is_rejected():
    orders = book()
    placed = orders.place("peas@sugarsnap.example", [LineItem("SSP-1001", 1)], day=DAY)
    with pytest.raises(Conflict):
        placed.transition_to("teleported")
    with pytest.raises(Conflict):
        orders.find_by_state("teleported")


def test_cancelled_orders_are_terminal():
    orders = book()
    placed = orders.place("peas@sugarsnap.example", [LineItem("SSP-1001", 1)], day=DAY)
    placed.transition_to("cancelled")
    assert placed.is_terminal()
    with pytest.raises(Conflict):
        placed.transition_to("paid")


def test_get_unknown_order():
    with pytest.raises(NotFound):
        book().get("ORD-20260824-000999")


def test_find_by_state_and_outstanding_total():
    orders = book()
    a = orders.place("a@sugarsnap.example", [LineItem("SSP-1001", 2)], day=DAY)   # 7.00
    b = orders.place("b@sugarsnap.example", [LineItem("SSP-1002", 2)], day=DAY)   # 4.50
    c = orders.place("c@sugarsnap.example", [LineItem("SSP-2001", 1)], day=DAY)   # 18.99
    orders.advance(b.order_id, "paid")
    orders.advance(c.order_id, "cancelled")
    assert [o.order_id for o in orders.find_by_state("new")] == [a.order_id]
    assert [o.order_id for o in orders.find_by_state("paid")] == [b.order_id]
    assert orders.outstanding_total() == Money.of("11.50", "USD")


def test_order_is_a_plain_mutable_record():
    orders = book()
    placed = orders.place("peas@sugarsnap.example", [LineItem("SSP-1001", 1)], day=DAY)
    assert isinstance(placed, Order)
    assert orders.get(placed.order_id) is placed
