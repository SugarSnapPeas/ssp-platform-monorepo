"""In-process end-to-end smoke test across every api module.

Referenced by ``test-selection-rules`` in
``services/api/.circleci/test-suites.yml`` with ``include: true``, so it is
always selected regardless of what changed.
"""

from datetime import date
from decimal import Decimal

from api.catalog import Catalog, Product, seed_catalog
from api.errors import BadRequest, error_payload
from api.orders import OrderBook
from api.pricing import LineItem, allocate_shipping, quote
from shared_core.money import Money, total

DAY = date(2026, 8, 24)


def test_full_basket_to_closed_order():
    catalog = seed_catalog()
    orders = OrderBook(catalog)

    placed = orders.place(
        "shopper@sugarsnap.example",
        [LineItem("SSP-1001", 12), LineItem("SSP-2001", 1)],
        tax_rate=Decimal("0.08"),
        promo="PODSQUAD",
        day=DAY,
    )

    # 12 x 3.50 = 42.00 less 5% = 39.90 ; 18.99 flat -> net 58.89
    assert placed.priced.gross == Money.of("60.99", "USD")
    assert placed.priced.line_discount == Money.of("2.10", "USD")
    assert placed.priced.promo_discount == Money.of("2.94", "USD")
    # 55.95 taxable + 8% (4.476 -> 4.48)
    assert placed.priced.tax == Money.of("4.48", "USD")
    assert placed.total == Money.of("60.43", "USD")

    shipping = allocate_shipping(placed.priced, Money.of("7.99", "USD"))
    assert total(shipping, "USD") == Money.of("7.99", "USD")

    for step in ("paid", "fulfilled", "closed"):
        orders.advance(placed.order_id, step)
    assert orders.get(placed.order_id).state == "closed"
    assert orders.outstanding_total().is_zero()


def test_custom_catalog_flows_through_pricing():
    catalog = Catalog([Product("AAA-0001", "Widget", Money.of("1.11", "GBP"))])
    priced = quote(catalog, [LineItem("AAA-0001", 50)])
    assert priced.currency == "GBP"
    assert priced.gross == Money.of("55.50", "GBP")
    assert priced.line_discount == Money.of("5.55", "GBP")
    assert priced.total == Money.of("49.95", "GBP")


def test_errors_serialise_for_the_wire():
    try:
        quote(seed_catalog(), [])
    except BadRequest as exc:
        payload = error_payload(exc)
    assert payload["error"]["status"] == 400
    assert payload["error"]["code"] == "bad_request"
