"""Product catalog. Imports shared-core for money and validation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence

from api.errors import Conflict, NotFound
from shared_core.ids import slugify
from shared_core.money import Money
from shared_core.validation import validate_sku

__all__ = ["Product", "Catalog", "seed_catalog"]


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    unit_price: Money
    active: bool = True
    tags: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sku", validate_sku(self.sku))
        object.__setattr__(self, "tags", tuple(sorted({t.strip().lower() for t in self.tags})))

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def has_tag(self, tag: str) -> bool:
        return tag.strip().lower() in self.tags


class Catalog:
    """An in-memory product catalog keyed by canonical SKU."""

    def __init__(self, products: Optional[Iterable[Product]] = None) -> None:
        self._products: Dict[str, Product] = {}
        for product in products or ():
            self.add(product)

    def __len__(self) -> int:
        return len(self._products)

    def __contains__(self, sku: str) -> bool:
        try:
            return validate_sku(sku) in self._products
        except Exception:
            return False

    def add(self, product: Product) -> Product:
        if product.sku in self._products:
            raise Conflict("duplicate sku {0}".format(product.sku), {"sku": product.sku})
        self._products[product.sku] = product
        return product

    def get(self, sku: str) -> Product:
        key = validate_sku(sku)
        try:
            return self._products[key]
        except KeyError:
            raise NotFound("no such product: {0}".format(key), {"sku": key}) from None

    def list_active(self) -> List[Product]:
        return [p for p in sorted(self._products.values(), key=lambda p: p.sku) if p.active]

    def search_by_tag(self, tag: str) -> List[Product]:
        return [p for p in self.list_active() if p.has_tag(tag)]

    def reprice(self, sku: str, unit_price: Money) -> Product:
        """Replace a product's price, returning the new product."""
        existing = self.get(sku)
        if unit_price.currency != existing.unit_price.currency:
            raise Conflict(
                "cannot reprice {0} from {1} to {2}".format(
                    existing.sku, existing.unit_price.currency, unit_price.currency
                ),
                {"sku": existing.sku},
            )
        if unit_price.is_negative():
            raise Conflict("price must not be negative", {"sku": existing.sku})
        updated = replace(existing, unit_price=unit_price)
        self._products[updated.sku] = updated
        return updated

    def deactivate(self, sku: str) -> Product:
        updated = replace(self.get(sku), active=False)
        self._products[updated.sku] = updated
        return updated

    def catalogue_value(self) -> Money:
        """Sum of the unit prices of all active products."""
        actives = self.list_active()
        if not actives:
            return Money.zero("USD")
        acc = Money.zero(actives[0].unit_price.currency)
        for product in actives:
            acc = acc + product.unit_price
        return acc


def seed_catalog() -> Catalog:
    """A small deterministic catalog used by tests and by the web service."""
    return Catalog(
        [
            Product("SSP-1001", "Sugar Snap Peas", Money.of("3.50", "USD"), tags=("veg", "fresh")),
            Product("SSP-1002", "Pea Shoots", Money.of("2.25", "USD"), tags=("veg", "fresh")),
            Product("SSP-2001", "Pea Protein Powder", Money.of("18.99", "USD"), tags=("pantry",)),
            Product("SSP-2002", "Discontinued Pod Rack", Money.of("9.00", "USD"), active=False),
        ]
    )
