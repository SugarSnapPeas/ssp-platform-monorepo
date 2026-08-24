"""Orders and their state machine. Imports shared-core (ids, validation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from api.catalog import Catalog
from api.errors import Conflict, NotFound
from api.pricing import LineItem, Quote, quote
from shared_core.ids import new_order_id, parse_order_id
from shared_core.money import Money
from shared_core.validation import validate_email

__all__ = ["Order", "OrderBook", "TRANSITIONS", "STATES"]

#: Legal state transitions for an order.
TRANSITIONS = {
    "new": ("paid", "cancelled"),
    "paid": ("fulfilled", "refunded"),
    "fulfilled": ("closed",),
    "cancelled": (),
    "refunded": (),
    "closed": (),
}

STATES = tuple(sorted(TRANSITIONS))


@dataclass
class Order:
    order_id: str
    customer_email: str
    priced: Quote
    state: str = "new"
    history: List[str] = field(default_factory=lambda: ["new"])

    @property
    def total(self) -> Money:
        return self.priced.total

    @property
    def placed_on(self) -> date:
        return parse_order_id(self.order_id).day

    def is_terminal(self) -> bool:
        return not TRANSITIONS[self.state]

    def transition_to(self, target: str) -> "Order":
        if target not in TRANSITIONS:
            raise Conflict("unknown order state {0!r}".format(target), {"state": target})
        if target not in TRANSITIONS[self.state]:
            raise Conflict(
                "cannot move order from {0} to {1}".format(self.state, target),
                {"order_id": self.order_id, "from": self.state, "to": target},
            )
        self.state = target
        self.history.append(target)
        return self


class OrderBook:
    """In-memory order store with a monotonically increasing sequence."""

    def __init__(self, catalog: Catalog, prefix: str = "ORD") -> None:
        self.catalog = catalog
        self.prefix = prefix
        self._sequence = 0
        self._orders: Dict[str, Order] = {}

    def __len__(self) -> int:
        return len(self._orders)

    def place(
        self,
        customer_email: str,
        items: Sequence[LineItem],
        tax_rate: Decimal = Decimal("0.00"),
        promo: Optional[str] = None,
        day: Optional[date] = None,
    ) -> Order:
        email = validate_email(customer_email)
        priced = quote(self.catalog, items, tax_rate=tax_rate, promo=promo)
        self._sequence += 1
        order = Order(
            order_id=new_order_id(self._sequence, prefix=self.prefix, day=day or date.today()),
            customer_email=email,
            priced=priced,
        )
        self._orders[order.order_id] = order
        return order

    def get(self, order_id: str) -> Order:
        try:
            return self._orders[order_id]
        except KeyError:
            raise NotFound("no such order: {0}".format(order_id), {"order_id": order_id}) from None

    def advance(self, order_id: str, target: str) -> Order:
        return self.get(order_id).transition_to(target)

    def find_by_state(self, state: str) -> List[Order]:
        if state not in TRANSITIONS:
            raise Conflict("unknown order state {0!r}".format(state), {"state": state})
        return [o for o in self._orders.values() if o.state == state]

    def outstanding_total(self, currency: str = "USD") -> Money:
        """Total value of orders that are placed but not yet fulfilled."""
        acc = Money.zero(currency)
        for order in self._orders.values():
            if order.state in ("new", "paid"):
                acc = acc + order.total
        return acc
