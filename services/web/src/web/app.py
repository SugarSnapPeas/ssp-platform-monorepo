"""In-process request dispatch. No HTTP anywhere — calls are direct.

Tests that go over the wire produce no coverage edges, so the whole web
surface is exercised by calling :meth:`App.handle` directly.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Mapping, Optional

from api.catalog import Catalog, seed_catalog
from api.errors import ApiError, BadRequest, NotFound
from web.routing import NoRoute, Router
from web.views import catalog_view, error_view, product_view, quote_view, render_quote_text

__all__ = ["App", "Response", "build_router"]


class Response(dict):
    """A dict with a ``status`` attribute, so assertions read nicely."""

    def __init__(self, status: int, body: Any) -> None:
        super().__init__(status=status, body=body)
        self.status = status
        self.body = body


def build_router() -> Router:
    return (
        Router()
        .add("GET", "/health", "health")
        .add("GET", "/products", "products")
        .add("GET", "/products/:sku", "product")
        .add("GET", "/tags/:tag", "tagged")
        .add("POST", "/quote", "quote")
        .add("GET", "/quote/:sku/:quantity:int", "quick_quote")
    )


class App:
    def __init__(self, catalog: Optional[Catalog] = None) -> None:
        self.catalog = catalog if catalog is not None else seed_catalog()
        self.router = build_router()

    def handle(self, method: str, path: str, body: Optional[Mapping[str, Any]] = None) -> Response:
        try:
            match = self.router.resolve(method, path)
        except NoRoute as exc:
            return Response(404, error_view(NotFound(str(exc)))["body"])
        try:
            handler = getattr(self, "_" + match.name)
            return Response(200, handler(match.params, body or {}))
        except ApiError as exc:
            view = error_view(exc)
            return Response(view["status"], view["body"])

    # -- handlers -------------------------------------------------------

    def _health(self, params, body):
        return {"status": "ok", "products": len(self.catalog)}

    def _products(self, params, body):
        return catalog_view(self.catalog)

    def _product(self, params, body):
        return product_view(self.catalog.get(params["sku"]))

    def _tagged(self, params, body):
        return catalog_view(self.catalog, tag=params["tag"])

    def _quote(self, params, body):
        basket = body.get("basket")
        if not isinstance(basket, dict):
            raise BadRequest("body.basket must be an object of sku -> quantity")
        view = quote_view(
            self.catalog,
            basket,
            tax_rate=Decimal(str(body.get("tax_rate", "0.00"))),
            promo=body.get("promo"),
            shipping=body.get("shipping"),
        )
        view["text"] = render_quote_text(view)
        return view

    def _quick_quote(self, params, body):
        return quote_view(self.catalog, {params["sku"]: params["quantity"]})

# demo: leaf-only change, should select only the web lane
# second commit: this IS a push to an open PR (synchronize event)
# retrigger after orb 1.0.1 (testsuite extension fix)
# retest with orb 1.0.3 (no legacy CLI install)
