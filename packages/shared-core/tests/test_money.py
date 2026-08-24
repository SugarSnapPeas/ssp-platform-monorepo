from decimal import Decimal

import pytest

from shared_core.money import CurrencyMismatch, Money, UnknownCurrency, total


def test_quantises_to_currency_minor_units():
    assert Money.of("1.005", "USD").amount == Decimal("1.00")  # banker's rounding
    assert Money.of("1.015", "USD").amount == Decimal("1.02")
    assert Money.of("1234.6", "JPY").amount == Decimal("1235")
    assert Money.of("1.23456", "KWD").amount == Decimal("1.235")


def test_currency_is_normalised_and_validated():
    assert Money.of("1", " usd ").currency == "USD"
    with pytest.raises(UnknownCurrency):
        Money.of("1", "XYZ")


def test_parse_round_trips_with_format():
    m = Money.parse("12.34 EUR")
    assert m == Money.of("12.34", "EUR")
    assert m.format() == "12.34 EUR"
    assert str(m) == "12.34 EUR"


@pytest.mark.parametrize("bad", ["12.34", "12.34 USD extra", "abc USD", ""])
def test_parse_rejects_malformed_input(bad):
    with pytest.raises(ValueError):
        Money.parse(bad)


def test_minor_unit_round_trip():
    assert Money.of("12.34", "USD").as_minor_units() == 1234
    assert Money.of("-12.34", "USD").as_minor_units() == -1234
    assert Money.of("1234", "JPY").as_minor_units() == 1234
    assert Money.from_minor_units(1234, "USD") == Money.of("12.34", "USD")
    with pytest.raises(TypeError):
        Money.from_minor_units(1.5, "USD")


def test_arithmetic():
    a = Money.of("10.00", "USD")
    b = Money.of("2.50", "USD")
    assert a + b == Money.of("12.50", "USD")
    assert a - b == Money.of("7.50", "USD")
    assert -b == Money.of("-2.50", "USD")
    assert abs(Money.of("-2.50", "USD")) == b
    assert a * 3 == Money.of("30.00", "USD")
    assert 3 * a == Money.of("30.00", "USD")
    assert a * Decimal("0.1") == Money.of("1.00", "USD")


def test_arithmetic_rejects_mismatched_currency_and_floats():
    usd = Money.of("1.00", "USD")
    eur = Money.of("1.00", "EUR")
    with pytest.raises(CurrencyMismatch):
        usd + eur
    with pytest.raises(CurrencyMismatch):
        usd < eur
    with pytest.raises(TypeError):
        usd + 1
    with pytest.raises(TypeError):
        usd * 1.5
    with pytest.raises(TypeError):
        Money.of(1.5, "USD")


def test_comparisons_and_predicates():
    small = Money.of("1.00", "USD")
    big = Money.of("2.00", "USD")
    assert small < big and small <= big
    assert big > small and big >= small
    assert Money.zero("USD").is_zero()
    assert Money.of("-1", "USD").is_negative()


def test_allocate_never_loses_a_minor_unit():
    parts = Money.of("0.05", "USD").allocate([3, 7])
    assert [p.amount for p in parts] == [Decimal("0.02"), Decimal("0.03")]
    assert sum((p.amount for p in parts), Decimal("0")) == Decimal("0.05")


def test_allocate_is_deterministic_on_ties():
    parts = Money.of("0.10", "USD").allocate([1, 1, 1])
    assert [p.as_minor_units() for p in parts] == [4, 3, 3]


def test_allocate_handles_negative_amounts():
    parts = Money.of("-0.05", "USD").allocate([3, 7])
    assert [p.as_minor_units() for p in parts] == [-2, -3]


def test_allocate_and_split_validation():
    m = Money.of("1.00", "USD")
    with pytest.raises(ValueError):
        m.allocate([])
    with pytest.raises(ValueError):
        m.allocate([0, 0])
    with pytest.raises(ValueError):
        m.allocate([-1, 2])
    with pytest.raises(TypeError):
        m.allocate([1, "2"])
    with pytest.raises(ValueError):
        m.split(0)
    with pytest.raises(TypeError):
        m.split("3")


def test_split_distributes_remainder():
    parts = Money.of("10.00", "USD").split(3)
    assert [p.format() for p in parts] == ["3.34 USD", "3.33 USD", "3.33 USD"]
    assert total(parts, "USD") == Money.of("10.00", "USD")


def test_total_of_empty_sequence_is_zero():
    assert total([], "GBP") == Money.zero("GBP")
