from datetime import date

import pytest

from shared_core.ids import OrderId, new_order_id, parse_order_id, short_hash, slugify


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Sugar Snap Peas", "sugar-snap-peas"),
        ("  Crème Brûlée  Tart! ", "creme-brulee-tart"),
        ("___underscores___", "underscores"),
        ("MiXeD CaSe 42", "mixed-case-42"),
        ("!!!", ""),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_slugify_truncates_without_trailing_hyphen():
    assert slugify("aaa bbb ccc", max_length=8) == "aaa-bbb"
    assert slugify("abcdefghij", max_length=4) == "abcd"


def test_slugify_validation():
    with pytest.raises(TypeError):
        slugify(None)
    with pytest.raises(ValueError):
        slugify("x", max_length=0)


def test_short_hash_is_stable_and_sized():
    assert short_hash("peapod") == short_hash("peapod")
    assert short_hash("peapod") != short_hash("peapods")
    assert len(short_hash("peapod", 12)) == 12
    with pytest.raises(ValueError):
        short_hash("x", 0)
    with pytest.raises(TypeError):
        short_hash(7)


def test_new_order_id_shape():
    assert new_order_id(42, day=date(2026, 8, 24)) == "ORD-20260824-000042"
    assert new_order_id(7, prefix="inv", day=date(2026, 1, 2)) == "INV-20260102-000007"


def test_new_order_id_validation():
    with pytest.raises(TypeError):
        new_order_id("1")
    with pytest.raises(ValueError):
        new_order_id(1000000)
    with pytest.raises(ValueError):
        new_order_id(1, prefix="X")


def test_order_id_round_trip():
    rendered = new_order_id(99, prefix="ORD", day=date(2026, 12, 31))
    parsed = parse_order_id(rendered)
    assert parsed == OrderId("ORD", date(2026, 12, 31), 99)
    assert parsed.render() == rendered
    assert str(parsed) == rendered


@pytest.mark.parametrize("bad", ["ORD-2026-000001", "ord-20260824-000001", "nope", ""])
def test_parse_order_id_rejects_garbage(bad):
    with pytest.raises(ValueError):
        parse_order_id(bad)


def test_parse_order_id_type_check():
    with pytest.raises(TypeError):
        parse_order_id(None)
