"""A minimal, exact money type built on :class:`decimal.Decimal`.

The point of this module for the demo is that it contains real, non-trivial,
independently testable behaviour (currency-aware quantisation and a
largest-remainder allocation that never loses or invents a minor unit), so
coverage edges from the service test suites into this file are genuine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import List, Sequence, Union

__all__ = [
    "Money",
    "CurrencyMismatch",
    "UnknownCurrency",
    "MINOR_UNIT_EXPONENTS",
]

#: Number of decimal places a currency is quantised to.
MINOR_UNIT_EXPONENTS = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "JPY": 0,
    "KWD": 3,
}

Numeric = Union[int, str, Decimal]


class CurrencyMismatch(ValueError):
    """Raised when two ``Money`` values of different currencies are combined."""


class UnknownCurrency(ValueError):
    """Raised for a currency code that has no configured minor-unit exponent."""


def exponent_for(currency: str) -> int:
    """Return the minor-unit exponent for ``currency``.

    >>> exponent_for("usd")
    2
    """
    code = (currency or "").strip().upper()
    if code not in MINOR_UNIT_EXPONENTS:
        raise UnknownCurrency("unknown currency: {0!r}".format(currency))
    return MINOR_UNIT_EXPONENTS[code]


@dataclass(frozen=True)
class Money:
    """An exact amount of a single currency.

    The amount is always quantised to the currency's minor unit using
    banker's rounding, so ``Money("1.005", "USD") == Money("1.00", "USD")``.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        code = (self.currency or "").strip().upper()
        exp = exponent_for(code)
        try:
            raw = self.amount if isinstance(self.amount, Decimal) else Decimal(str(self.amount))
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError("not a valid amount: {0!r}".format(self.amount)) from exc
        if not raw.is_finite():
            raise ValueError("amount must be finite, got {0!r}".format(self.amount))
        quantised = raw.quantize(Decimal(1).scaleb(-exp), rounding=ROUND_HALF_EVEN)
        object.__setattr__(self, "amount", quantised)
        object.__setattr__(self, "currency", code)

    # -- constructors ---------------------------------------------------

    @classmethod
    def of(cls, amount: Numeric, currency: str) -> "Money":
        """Build a ``Money`` from anything ``Decimal`` accepts."""
        if isinstance(amount, float):  # pragma: no cover - guarded by type check below
            raise TypeError("refusing to build Money from a float; pass a str or Decimal")
        return cls(Decimal(str(amount)), currency)

    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(Decimal("0"), currency)

    @classmethod
    def from_minor_units(cls, minor: int, currency: str) -> "Money":
        """Build from an integer number of minor units (cents, yen, fils)."""
        if not isinstance(minor, int) or isinstance(minor, bool):
            raise TypeError("minor units must be an int")
        exp = exponent_for(currency)
        return cls(Decimal(minor).scaleb(-exp), currency)

    @classmethod
    def parse(cls, text: str) -> "Money":
        """Parse ``"12.34 USD"`` (amount first, single space, ISO code)."""
        if not isinstance(text, str):
            raise TypeError("parse() expects a string")
        parts = text.strip().split()
        if len(parts) != 2:
            raise ValueError("cannot parse money from {0!r}".format(text))
        raw, code = parts
        try:
            amount = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("cannot parse amount from {0!r}".format(text)) from exc
        return cls(amount, code)

    # -- accessors ------------------------------------------------------

    def as_minor_units(self) -> int:
        """Exact integer number of minor units."""
        exp = exponent_for(self.currency)
        return int(self.amount.scaleb(exp).to_integral_value())

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_negative(self) -> bool:
        return self.amount < 0

    # -- arithmetic -----------------------------------------------------

    def _check(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError("expected Money, got {0}".format(type(other).__name__))
        if other.currency != self.currency:
            raise CurrencyMismatch(
                "cannot combine {0} and {1}".format(self.currency, other.currency)
            )

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount), self.currency)

    def __mul__(self, factor: Numeric) -> "Money":
        if isinstance(factor, float):
            raise TypeError("refusing to multiply Money by a float")
        if isinstance(factor, bool) or not isinstance(factor, (int, str, Decimal)):
            raise TypeError("cannot multiply Money by {0}".format(type(factor).__name__))
        return Money(self.amount * Decimal(str(factor)), self.currency)

    __rmul__ = __mul__

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.amount >= other.amount

    # -- splitting ------------------------------------------------------

    def allocate(self, weights: Sequence[int]) -> List["Money"]:
        """Split into parts proportional to ``weights``, losing nothing.

        Uses the largest-remainder method: the sum of the returned parts is
        always exactly equal to ``self``. Ties are broken by position, so the
        result is deterministic.

        >>> [str(m.amount) for m in Money.parse("0.05 USD").allocate([3, 7])]
        ['0.02', '0.03']
        """
        if not weights:
            raise ValueError("allocate() needs at least one weight")
        if any(not isinstance(w, int) or isinstance(w, bool) for w in weights):
            raise TypeError("weights must be ints")
        if any(w < 0 for w in weights):
            raise ValueError("weights must not be negative")
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("weights must not sum to zero")

        minor = self.as_minor_units()
        sign = -1 if minor < 0 else 1
        magnitude = abs(minor)

        base = [magnitude * w // total_weight for w in weights]
        remainder = magnitude - sum(base)
        order = sorted(
            range(len(weights)),
            key=lambda i: (-((magnitude * weights[i]) % total_weight), i),
        )
        for i in range(remainder):
            base[order[i]] += 1
        return [Money.from_minor_units(sign * b, self.currency) for b in base]

    def split(self, parts: int) -> List["Money"]:
        """Split evenly into ``parts``, distributing the remainder fairly."""
        if not isinstance(parts, int) or isinstance(parts, bool):
            raise TypeError("parts must be an int")
        if parts < 1:
            raise ValueError("parts must be >= 1")
        return self.allocate([1] * parts)

    # -- rendering ------------------------------------------------------

    def format(self) -> str:
        """Human-readable ``"12.34 USD"``."""
        return "{0} {1}".format(self.amount, self.currency)

    def __str__(self) -> str:
        return self.format()


def total(items: Sequence[Money], currency: str) -> Money:
    """Sum ``items``, returning ``Money.zero(currency)`` for an empty sequence."""
    acc = Money.zero(currency)
    for item in items:
        acc = acc + item
    return acc
