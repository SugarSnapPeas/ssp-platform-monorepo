"""worker.reporting tests: shared-core edge WITHOUT going through api."""

import pytest

from shared_core.money import Money
from worker.reporting import Bucket, bucket_by, running_total, top_n


def rows():
    return [
        ("Fresh Peas", Money.of("3.50", "USD")),
        ("Pantry", Money.of("18.99", "USD")),
        ("Fresh Peas", Money.of("2.25", "USD")),
        ("Gift Boxes", Money.of("5.75", "USD")),
    ]


def test_bucket_by_groups_and_sorts_by_amount_desc():
    buckets = bucket_by(rows(), "USD")
    # Fresh Peas and Gift Boxes both total 5.75, so the alphabetical
    # tie-break decides the order.
    assert [(b.key, b.count, b.amount.format()) for b in buckets] == [
        ("Pantry", 1, "18.99 USD"),
        ("Fresh Peas", 2, "5.75 USD"),
        ("Gift Boxes", 1, "5.75 USD"),
    ]


def test_bucket_slug_uses_shared_core():
    assert bucket_by([("Fresh Peas", Money.of("1", "USD"))], "USD")[0].slug == "fresh-peas"


def test_bucket_by_rejects_mixed_currencies():
    with pytest.raises(ValueError):
        bucket_by([("a", Money.of("1", "USD")), ("b", Money.of("1", "EUR"))], "USD")


def test_bucket_by_empty():
    assert bucket_by([], "USD") == []


def test_top_n_returns_head_and_remainder():
    buckets = bucket_by(rows(), "USD")
    head, rest = top_n(buckets, 1, "USD")
    assert [b.key for b in head] == ["Pantry"]
    assert rest == Money.of("11.50", "USD")


def test_top_n_edges():
    buckets = bucket_by(rows(), "USD")
    head, rest = top_n(buckets, 0, "USD")
    assert head == [] and rest == Money.of("30.49", "USD")
    head, rest = top_n(buckets, 99, "USD")
    assert len(head) == 3 and rest == Money.zero("USD")


def test_top_n_validation():
    with pytest.raises(TypeError):
        top_n([], True, "USD")
    with pytest.raises(ValueError):
        top_n([], -1, "USD")


def test_running_total_ends_at_the_grand_total():
    amounts = [Money.of("1.00", "USD"), Money.of("2.50", "USD"), Money.of("0.25", "USD")]
    assert [m.format() for m in running_total(amounts, "USD")] == [
        "1.00 USD",
        "3.50 USD",
        "3.75 USD",
    ]
    assert running_total([], "USD") == []


def test_bucket_equality_is_value_based():
    assert Bucket("a", 1, Money.of("1", "USD")) == Bucket("a", 1, Money.of("1.00", "USD"))
