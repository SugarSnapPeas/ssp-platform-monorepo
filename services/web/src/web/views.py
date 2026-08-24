"""View functions.

Imports ``api`` ONLY — never ``shared_core`` directly. web's dependency on
shared-core is real but purely transitive, through api. That is what
``graph.json`` records ("web depends_on api"), and it is why a shared-core
change must still select the web lane.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Mapping, Optional, Sequence

from api.catalog import Catalog, Product
from api.errors import ApiError, BadRequest, NotFound, error_payload
from api.pricing import LineItem, Quote, allocate_shipping, quote
from web.templating import render, render_rows

__all__ = [
    "product_view",
    "catalog_view",
    "quote_view",
    "render_quote_text",
    "error_view",
]

LINE_TEMPLATE = "{{ quantity }} x {{ name }} @ {{ unit_price }} = {{ net }}"


def product_view(product: Product) -> Dict[str, object]:
    """Serialise a product for the web layer."""
    return {
        "sku": product.sku,
        "slug": product.slug,
        "name": product.name,
        "unit_price": product.unit_price.format(),
        "tags": list(product.tags),
        "active": product.active,
    }


def catalog_view(catalog: Catalog, tag: Optional[str] = None) -> Dict[str, object]:
    products = catalog.search_by_tag(tag) if tag else catalog.list_active()
    return {
        "count": len(products),
        "tag": tag,
        "products": [product_view(p) for p in products],
        "total_value": catalog.catalogue_value().format(),
    }


def quote_view(
    catalog: Catalog,
    basket: Mapping[str, int],
    tax_rate: Decimal = Decimal("0.00"),
    promo: Optional[str] = None,
    shipping: Optional[str] = None,
) -> Dict[str, object]:
    """Price a ``{sku: quantity}`` basket and shape it for rendering."""
    if not basket:
        raise BadRequest("basket is empty")
    items = [LineItem(sku, qty) for sku, qty in sorted(basket.items())]
    priced = quote(catalog, items, tax_rate=tax_rate, promo=promo)

    lines: List[Dict[str, object]] = []
    for line in priced.lines:
        lines.append(
            {
                "sku": line.sku,
                "name": line.name,
                "quantity": line.quantity,
                "unit_price": line.unit_price.format(),
                "discount": line.discount.format(),
                "net": line.net.format(),
            }
        )

    view: Dict[str, object] = {
        "currency": priced.currency,
        "lines": lines,
        "gross": priced.gross.format(),
        "discount_total": priced.discount_total.format(),
        "tax": priced.tax.format(),
        "total": priced.total.format(),
    }
    if shipping is not None:
        parts = allocate_shipping(priced, _money_like(priced, shipping))
        view["shipping"] = [p.format() for p in parts]
    return view


def _money_like(priced: Quote, amount: str):
    """Build a Money in the quote's currency without importing shared_core.

    The type comes back out of api's own objects, which keeps web's import
    graph honest: web talks to api, api talks to shared-core.
    """
    template = priced.lines[0].unit_price
    return type(template)(amount, priced.currency)


def render_quote_text(view: Mapping[str, object]) -> str:
    """Render a quote view as plain text using the web templating module."""
    body = render_rows(LINE_TEMPLATE, view["lines"])
    footer = render(
        "subtotal {{ gross }} / discount {{ discount_total }} / tax {{ tax }} / total {{ total }}",
        view,
    )
    return body + "\n" + footer


def error_view(error: ApiError) -> Dict[str, object]:
    """Turn an api error into a web response body plus status."""
    payload = error_payload(error)
    payload["error"]["title"] = render(
        "{{ reason }}: {{ message }}",
        {"reason": payload["error"]["reason"], "message": payload["error"]["message"]},
    )
    return {"status": error.status, "body": payload}
