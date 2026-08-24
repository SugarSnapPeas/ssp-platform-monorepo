"""api.pricing tests — the heaviest shared-core (Money) consumer in api."""

from decimal import Decimal

import pytest

from api.catalog import seed_catalog
from api.errors import BadRequest
from api.pricing import LineItem, allocate_shipping, quote, volume_discount_rate
from shared_core.money import Money
from shared_core.validation import ValidationError


@pytest.mark.parametrize(
    "quantity,rate",
    [(1, "0.00"), (9, "0.00"), (10, "0.05"), (49, "0.05"), (50, "0.10"), (100, "0.15"), (999, "0.15")],
)
def test_volume_discount_tiers(quantity, rate):
    assert volume_discount_rate(quantity) == Decimal(rate)


def test_volume_discount_rejects_bad_quantity():
    with pytest.raises(ValidationError):
        volume_discount_rate(0)


def test_line_item_normalises_and_validates():
    item = LineItem("ssp-1001", 3)
    assert item.sku == "SSP-1001"
    with pytest.raises(ValidationError):
        LineItem("SSP-1001", 0)
    with pytest.raises(ValidationError):
        LineItem("bad", 1)


def test_simple_quote_without_discount_or_tax():
    priced = quote(seed_catalog(), [LineItem("SSP-1001", 2)])
    assert priced.currency == "USD"
    assert priced.gross == Money.of("7.00", "USD")
    assert priced.line_discount == Money.zero("USD")
    assert priced.tax == Money.zero("USD")
    assert priced.total == Money.of("7.00", "USD")
    assert priced.line_for("ssp-1001").net == Money.of("7.00", "USD")


def test_volume_discount_applies_per_line():
    priced = quote(seed_catalog(), [LineItem("SSP-1001", 10), LineItem("SSP-1002", 1)])
    # 10 x 3.50 = 35.00, 5% off = 1.75;  1 x 2.25 = 2.25, no discount
    assert priced.gross == Money.of("37.25", "USD")
    assert priced.line_discount == Money.of("1.75", "USD")
    assert priced.total == Money.of("35.50", "USD")


def test_promo_stacks_on_top_of_line_discounts():
    priced = quote(seed_catalog(), [LineItem("SSP-1001", 10)], promo="snappy10")
    assert priced.line_discount == Money.of("1.75", "USD")
    # 10% of the 33.25 net is 3.325, which banker's rounding takes to 3.32.
    assert priced.promo_discount == Money.of("3.32", "USD")
    assert priced.discount_total == Money.of("5.07", "USD")
    assert priced.total == Money.of("29.93", "USD")


def test_tax_applies_after_all_discounts():
    priced = quote(seed_catalog(), [LineItem("SSP-1002", 4)], tax_rate=Decimal("0.20"))
    assert priced.gross == Money.of("9.00", "USD")
    assert priced.tax == Money.of("1.80", "USD")
    assert priced.total == Money.of("10.80", "USD")


@pytest.mark.parametrize(
    "kwargs,items",
    [
        ({}, []),
        ({"tax_rate": Decimal("-0.1")}, [LineItem("SSP-1001", 1)]),
        ({"tax_rate": Decimal("1.5")}, [LineItem("SSP-1001", 1)]),
        ({"promo": "NOPE"}, [LineItem("SSP-1001", 1)]),
    ],
)
def test_quote_rejects_bad_input(kwargs, items):
    with pytest.raises(BadRequest):
        quote(seed_catalog(), items, **kwargs)


def test_quote_rejects_duplicate_lines_and_inactive_products():
    catalog = seed_catalog()
    with pytest.raises(BadRequest):
        quote(catalog, [LineItem("SSP-1001", 1), LineItem("ssp-1001", 2)])
    with pytest.raises(BadRequest):
        quote(catalog, [LineItem("SSP-2002", 1)])


def test_line_for_missing_sku():
    priced = quote(seed_catalog(), [LineItem("SSP-1001", 1)])
    with pytest.raises(BadRequest):
        priced.line_for("SSP-2001")


def test_allocate_shipping_sums_exactly_to_the_shipping_charge():
    priced = quote(seed_catalog(), [LineItem("SSP-1001", 1), LineItem("SSP-1002", 1)])
    parts = allocate_shipping(priced, Money.of("5.00", "USD"))
    # 350:225 of 500 minor units -> 304 / 195 with one unit left over, which
    # largest-remainder awards to the second line (375 > 200).
    assert [p.format() for p in parts] == ["3.04 USD", "1.96 USD"]
    assert parts[0] + parts[1] == Money.of("5.00", "USD")


def test_allocate_shipping_guards():
    priced = quote(seed_catalog(), [LineItem("SSP-1001", 1)])
    with pytest.raises(BadRequest):
        allocate_shipping(priced, Money.of("5.00", "EUR"))
    with pytest.raises(BadRequest):
        allocate_shipping(priced, Money.of("-1.00", "USD"))


def test_allocate_shipping_falls_back_to_even_split_on_zero_value_basket():
    catalog = seed_catalog()
    catalog.reprice("SSP-1001", Money.zero("USD"))
    catalog.reprice("SSP-1002", Money.zero("USD"))
    priced = quote(catalog, [LineItem("SSP-1001", 1), LineItem("SSP-1002", 1)])
    parts = allocate_shipping(priced, Money.of("5.01", "USD"))
    assert [p.as_minor_units() for p in parts] == [251, 250]
