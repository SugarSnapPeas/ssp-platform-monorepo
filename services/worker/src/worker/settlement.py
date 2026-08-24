"""Merchant settlement: splits order revenue between parties.

Imports ``api.pricing`` and ``shared_core.money``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Mapping, Sequence

from api.errors import BadRequest
from api.orders import Order
from api.pricing import Quote
from shared_core.money import Money, total

__all__ = ["Payout", "SettlementRun", "settle", "platform_fee"]

#: Platform take rate.
PLATFORM_FEE_RATE = Decimal("0.029")


@dataclass(frozen=True)
class Payout:
    party: str
    amount: Money


@dataclass(frozen=True)
class SettlementRun:
    currency: str
    gross: Money
    fee: Money
    payouts: Sequence[Payout]

    @property
    def net(self) -> Money:
        return total([p.amount for p in self.payouts], self.currency)

    def balances(self) -> bool:
        """Fee plus payouts must equal gross, to the minor unit."""
        return self.fee + self.net == self.gross


def platform_fee(amount: Money) -> Money:
    """The platform's cut of ``amount``."""
    if amount.is_negative():
        raise BadRequest("cannot take a fee from a negative amount")
    return amount * PLATFORM_FEE_RATE


def settle(priced: Quote, shares: Mapping[str, int]) -> SettlementRun:
    """Split a quote's total between ``shares`` after the platform fee.

    ``shares`` maps a party name to an integer weight. The payouts are
    allocated with :meth:`shared_core.money.Money.allocate`, so nothing is
    lost to rounding.
    """
    if not shares:
        raise BadRequest("settlement needs at least one party")
    parties = sorted(shares)
    weights = [shares[p] for p in parties]
    if any(w < 0 for w in weights):
        raise BadRequest("share weights must not be negative")
    if sum(weights) == 0:
        raise BadRequest("share weights must not sum to zero")

    gross = priced.total
    fee = platform_fee(gross)
    distributable = gross - fee
    amounts = distributable.allocate(weights)
    return SettlementRun(
        currency=priced.currency,
        gross=gross,
        fee=fee,
        payouts=tuple(Payout(p, a) for p, a in zip(parties, amounts)),
    )


def settle_orders(orders: Sequence[Order], shares: Mapping[str, int]) -> List[SettlementRun]:
    """Settle every order that has reached ``fulfilled`` or ``closed``."""
    return [settle(o.priced, shares) for o in orders if o.state in ("fulfilled", "closed")]
