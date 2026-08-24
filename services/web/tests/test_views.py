"""web.views tests: the genuine api edge for the web lane.

Note that this file imports ``api`` but never ``shared_core``. shared-core is
still reached at runtime, transitively through api, so coverage records an
edge into ``packages/shared-core`` from here.
"""

from decimal import Decimal

import pytest

from api.catalog import Catalog, Product, seed_catalog
from api.errors import BadRequest, NotFound
from web.views import catalog_view, error_view, product_view, quote_view, render_quote_text


def test_product_view_shape():
    product = seed_catalog().get("SSP-1001")
    assert product_view(product) == {
        "sku": "SSP-1001",
        "slug": "sugar-snap-peas",
        "name": "Sugar Snap Peas",
        "unit_price": "3.50 USD",
        "tags": ["fresh", "veg"],
        "active": True,
    }


def test_catalog_view_lists_active_products_only():
    view = catalog_view(seed_catalog())
    assert view["count"] == 3
    assert view["tag"] is None
    assert [p["sku"] for p in view["products"]] == ["SSP-1001", "SSP-1002", "SSP-2001"]
    assert view["total_value"] == "24.74 USD"


def test_catalog_view_filters_by_tag():
    view = catalog_view(seed_catalog(), tag="pantry")
    assert view["count"] == 1
    assert view["products"][0]["sku"] == "SSP-2001"


def test_quote_view_prices_a_basket():
    view = quote_view(seed_catalog(), {"SSP-1001": 10})
    assert view["currency"] == "USD"
    assert view["gross"] == "35.00 USD"
    assert view["discount_total"] == "1.75 USD"
    assert view["total"] == "33.25 USD"
    assert view["lines"][0]["net"] == "33.25 USD"


def test_quote_view_applies_tax_and_promo():
    view = quote_view(
        seed_catalog(), {"SSP-1001": 10}, tax_rate=Decimal("0.10"), promo="PODSQUAD"
    )
    assert view["discount_total"] == "3.41 USD"
    assert view["tax"] == "3.16 USD"
    assert view["total"] == "34.75 USD"


def test_quote_view_allocates_shipping_exactly():
    view = quote_view(seed_catalog(), {"SSP-1001": 1, "SSP-1002": 1}, shipping="5.00")
    assert view["shipping"] == ["3.04 USD", "1.96 USD"]


def test_quote_view_sorts_lines_by_sku():
    view = quote_view(seed_catalog(), {"SSP-2001": 1, "SSP-1001": 1})
    assert [line["sku"] for line in view["lines"]] == ["SSP-1001", "SSP-2001"]


def test_quote_view_rejects_an_empty_basket():
    with pytest.raises(BadRequest):
        quote_view(seed_catalog(), {})


def test_quote_view_propagates_api_errors():
    with pytest.raises(NotFound):
        quote_view(seed_catalog(), {"SSP-9999": 1})
    with pytest.raises(BadRequest):
        quote_view(seed_catalog(), {"SSP-2002": 1})  # inactive product


def test_render_quote_text():
    view = quote_view(seed_catalog(), {"SSP-1001": 2})
    text = render_quote_text(view)
    assert text.splitlines() == [
        "2 x Sugar Snap Peas @ 3.50 USD = 7.00 USD",
        "subtotal 7.00 USD / discount 0.00 USD / tax 0.00 USD / total 7.00 USD",
    ]


def test_error_view_adds_a_human_title():
    view = error_view(NotFound("no such product: SSP-9999"))
    assert view["status"] == 404
    assert view["body"]["error"]["title"] == "Not Found: no such product: SSP-9999"


def test_views_work_against_an_injected_catalog():
    # The price object comes back out of api rather than being constructed
    # here, which keeps this module free of any direct shared_core import.
    unit_price = seed_catalog().get("SSP-1001").unit_price
    catalog = Catalog([Product("AAA-0001", "Widget", unit_price, tags=("misc",))])
    view = quote_view(catalog, {"AAA-0001": 2})
    assert view["total"] == "7.00 USD"
    assert catalog_view(catalog, tag="misc")["count"] == 1
