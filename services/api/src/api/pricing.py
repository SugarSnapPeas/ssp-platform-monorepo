"""Quote calculation. Imports shared-core heavily (Money, validation)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from api.catalog import Catalog
from api.errors import BadRequest
from shared_core.money import Money
from shared_core.validation import validate_quantity, validate_sku

__all__ = [
    "LineItem",
    "QuoteLine",
    "Quote",
    "VOLUME_TIERS",
    "PROMOS",
    "volume_discount_rate",
    "quote",
    "allocate_shipping",
]

#: ``(minimum quantity, discount rate)``, highest tier last.
VOLUME_TIERS: Tuple[Tuple[int, Decimal], ...] = (
    (1, Decimal("0.00")),
    (10, Decimal("0.05")),
    (50, Decimal("0.10")),
    (100, Decimal("0.15")),
)

#: Promo code -> additional order-level discount rate.
PROMOS = {
    "PODSQUAD": Decimal("0.05"),
    "SNAPPY10": Decimal("0.10"),
}


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "sku", validate_sku(self.sku))
        object.__setattr__(self, "quantity", validate_quantity(self.quantity))


@dataclass(frozen=True)
class QuoteLine:
    sku: str
    name: str
    quantity: int
    unit_price: Money
    gross: Money
    discount: Money

    @property
    def net(self) -> Money:
        return self.gross - self.discount


@dataclass(frozen=True)
class Quote:
    lines: Sequence[QuoteLine]
    currency: str
    gross: Money
    line_discount: Money
    promo_discount: Money
    tax: Money
    total: Money

    @property
    def discount_total(self) -> Money:
        return self.line_discount + self.promo_discount

    def line_for(self, sku: str) -> QuoteLine:
        key = validate_sku(sku)
        for line in self.lines:
            if line.sku == key:
                return line
        raise BadRequest("quote has no line for {0}".format(key), {"sku": key})


def volume_discount_rate(quantity: int) -> Decimal:
    """Highest tier rate whose threshold ``quantity`` reaches.

    >>> volume_discount_rate(10)
    Decimal('0.05')
    """
    validate_quantity(quantity)
    rate = Decimal("0.00")
    for threshold, tier_rate in VOLUME_TIERS:
        if quantity >= threshold:
            rate = tier_rate
    return rate


def quote(
    catalog: Catalog,
    items: Sequence[LineItem],
    tax_rate: Decimal = Decimal("0.00"),
    promo: Optional[str] = None,
) -> Quote:
    """Price ``items`` against ``catalog``.

    Line-level volume discounts are applied first, then an order-level promo,
    then tax on the discounted subtotal.
    """
    if not items:
        raise BadRequest("cannot quote an empty basket")
    if tax_rate < 0 or tax_rate > 1:
        raise BadRequest("tax_rate must be between 0 and 1, got {0}".format(tax_rate))

    seen = set()
    lines: List[QuoteLine] = []
    currency: Optional[str] = None

    for item in items:
        if item.sku in seen:
            raise BadRequest("duplicate line for {0}".format(item.sku), {"sku": item.sku})
        seen.add(item.sku)
        product = catalog.get(item.sku)
        if not product.active:
            raise BadRequest("product {0} is not active".format(product.sku), {"sku": product.sku})
        if currency is None:
            currency = product.unit_price.currency
        gross = product.unit_price * item.quantity
        discount = gross * volume_discount_rate(item.quantity)
        lines.append(
            QuoteLine(
                sku=product.sku,
                name=product.name,
                quantity=item.quantity,
                unit_price=product.unit_price,
                gross=gross,
                discount=discount,
            )
        )

    assert currency is not None
    zero = Money.zero(currency)
    gross_total = zero
    line_discount = zero
    for line in lines:
        gross_total = gross_total + line.gross
        line_discount = line_discount + line.discount

    net = gross_total - line_discount
    promo_discount = zero
    if promo is not None:
        key = promo.strip().upper()
        if key not in PROMOS:
            raise BadRequest("unknown promo code {0!r}".format(promo), {"promo": key})
        promo_discount = net * PROMOS[key]

    taxable = net - promo_discount
    tax = taxable * tax_rate
    return Quote(
        lines=tuple(lines),
        currency=currency,
        gross=gross_total,
        line_discount=line_discount,
        promo_discount=promo_discount,
        tax=tax,
        total=taxable + tax,
    )


def allocate_shipping(priced: Quote, shipping: Money) -> List[Money]:
    """Spread ``shipping`` across the quote's lines by gross value.

    Uses :meth:`shared_core.money.Money.allocate`, so the parts always sum to
    exactly ``shipping``.
    """
    if shipping.currency != priced.currency:
        raise BadRequest(
            "shipping is {0} but the quote is {1}".format(shipping.currency, priced.currency)
        )
    if shipping.is_negative():
        raise BadRequest("shipping must not be negative")
    weights = [line.gross.as_minor_units() for line in priced.lines]
    if sum(weights) == 0:
        return list(shipping.split(len(priced.lines)))
    return shipping.allocate(weights)
