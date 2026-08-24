import pytest

from shared_core.validation import (
    ValidationError,
    collect_errors,
    ensure_range,
    require,
    validate_email,
    validate_quantity,
    validate_sku,
)


def test_require_accepts_real_values():
    assert require("x", "f") == "x"
    assert require(0, "f") == 0
    assert require([], "f") == []


@pytest.mark.parametrize("bad,code", [(None, "missing"), ("", "blank"), ("   ", "blank")])
def test_require_rejects_empty(bad, code):
    with pytest.raises(ValidationError) as exc:
        require(bad, "widget")
    assert exc.value.field == "widget"
    assert exc.value.code == code


def test_ensure_range():
    assert ensure_range(5, "n", minimum=1, maximum=10) == 5
    with pytest.raises(ValidationError) as low:
        ensure_range(0, "n", minimum=1)
    assert low.value.code == "below_minimum"
    with pytest.raises(ValidationError) as high:
        ensure_range(11, "n", maximum=10)
    assert high.value.code == "above_maximum"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ABC-1234", "ABC-1234"),
        ("  abc-1234  ", "ABC-1234"),
        ("XYZ-0001-A9", "XYZ-0001-A9"),
    ],
)
def test_validate_sku_normalises(raw, expected):
    assert validate_sku(raw) == expected


@pytest.mark.parametrize("bad", ["AB-1234", "ABCD-1234", "ABC-123", "ABC1234", "ABC-1234-ABC"])
def test_validate_sku_rejects_bad_format(bad):
    with pytest.raises(ValidationError) as exc:
        validate_sku(bad)
    assert exc.value.code == "format"


def test_validate_sku_type_and_blank():
    with pytest.raises(ValidationError):
        validate_sku(None)
    with pytest.raises(ValidationError):
        validate_sku(1234)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("peas@sugarsnap.example", "peas@sugarsnap.example"),
        ("  Pod.Person+tag@Mail.SugarSnap.EXAMPLE ", "Pod.Person+tag@mail.sugarsnap.example"),
    ],
)
def test_validate_email_normalises_domain_only(raw, expected):
    assert validate_email(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "no-at-sign.example",
        "two@at@signs.example",
        "@nolocal.example",
        "nodomaindot@example",
        "sp ace@sugarsnap.example",
        ".leading@sugarsnap.example",
        "trailing.@sugarsnap.example",
        "double..dot@sugarsnap.example",
        "peas@-badlabel.example",
        "peas@sugarsnap.e",
        "peas@sugarsnap.12",
    ],
)
def test_validate_email_rejects(bad):
    with pytest.raises(ValidationError) as exc:
        validate_email(bad)
    assert exc.value.code in {"format", "missing", "blank"}


def test_validate_email_local_part_length():
    with pytest.raises(ValidationError):
        validate_email("a" * 65 + "@sugarsnap.example")


def test_validate_quantity():
    assert validate_quantity(1) == 1
    assert validate_quantity(999) == 999
    for bad in (0, 1000, -3):
        with pytest.raises(ValidationError):
            validate_quantity(bad)
    for bad in (True, "2", 2.0):
        with pytest.raises(ValidationError):
            validate_quantity(bad)


def test_collect_errors_does_not_short_circuit():
    errors = collect_errors(
        [
            lambda: validate_sku("nope"),
            lambda: validate_email("also-nope"),
            lambda: validate_quantity(5),
        ]
    )
    assert [e.field for e in errors] == ["sku", "email"]
    assert errors[0].as_dict()["code"] == "format"
