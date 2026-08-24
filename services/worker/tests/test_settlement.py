"""worker.settlement tests: api.pricing + shared_core.money edge."""

from decimal import Decimal

import pytest

from api.catalog import seed_catalog
from api.errors import BadRequest
from api.orders import OrderBook
from api.pricing import LineItem, quote
from shared_core.money import Money
from worker.settlement import PLATFORM_FEE_RATE, platform_fee, settle, settle_orders


def priced_basket(quantity=10):
    return quote(seed_catalog(), [LineItem("SSP-1001", quantity)])


def test_platform_fee_rate_is_applied_with_bankers_rounding():
    assert PLATFORM_FEE_RATE == Decimal("0.029")
    # 33.25 * 0.029 = 0.96425 -> 0.96
    assert platform_fee(Money.of("33.25", "USD")) == Money.of("0.96", "USD")
    assert platform_fee(Money.zero("USD")).is_zero()


def test_platform_fee_rejects_negative_amounts():
    with pytest.raises(BadRequest):
        platform_fee(Money.of("-1.00", "USD"))


def test_settle_balances_exactly():
    run = settle(priced_basket(), {"merchant": 8, "affiliate": 2})
    assert run.gross == Money.of("33.25", "USD")
    assert run.fee == Money.of("0.96", "USD")
    assert run.balances()
    assert run.net == Money.of("32.29", "USD")


def test_settle_allocates_by_weight_and_sorts_parties():
    run = settle(priced_basket(), {"merchant": 8, "affiliate": 2})
    assert [(p.party, p.amount.format()) for p in run.payouts] == [
        ("affiliate", "6.46 USD"),
        ("merchant", "25.83 USD"),
    ]


def test_settle_never_loses_a_cent_on_awkward_splits():
    run = settle(priced_basket(quantity=3), {"a": 1, "b": 1, "c": 1})
    assert run.balances()
    assert sum(p.amount.as_minor_units() for p in run.payouts) == run.net.as_minor_units()


@pytest.mark.parametrize(
    "shares", [{}, {"a": -1, "b": 2}, {"a": 0, "b": 0}]
)
def test_settle_rejects_bad_share_maps(shares):
    with pytest.raises(BadRequest):
        settle(priced_basket(), shares)


def test_settle_single_party_takes_everything_after_the_fee():
    run = settle(priced_basket(), {"merchant": 1})
    assert run.payouts[0].amount == run.gross - run.fee
    assert run.balances()


def test_settle_orders_only_settles_completed_orders():
    orders = OrderBook(seed_catalog())
    a = orders.place("a@sugarsnap.example", [LineItem("SSP-1001", 1)])
    b = orders.place("b@sugarsnap.example", [LineItem("SSP-1002", 1)])
    c = orders.place("c@sugarsnap.example", [LineItem("SSP-2001", 1)])
    for step in ("paid", "fulfilled"):
        orders.advance(b.order_id, step)
    for step in ("paid", "fulfilled", "closed"):
        orders.advance(c.order_id, step)

    runs = settle_orders([a, b, c], {"merchant": 1})
    assert len(runs) == 2
    assert [r.gross.format() for r in runs] == ["2.25 USD", "18.99 USD"]
    assert all(r.balances() for r in runs)


def test_settle_orders_with_nothing_to_settle():
    assert settle_orders([], {"merchant": 1}) == []
