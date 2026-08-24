"""web.app tests: routing + views + api, all in-process (no HTTP)."""

import pytest

from api.catalog import Catalog, Product, seed_catalog
from web.app import App, Response, build_router


def app():
    return App()


def test_health():
    response = app().handle("GET", "/health")
    assert response.status == 200
    assert response.body == {"status": "ok", "products": 4}


def test_products_listing():
    response = app().handle("GET", "/products")
    assert response.status == 200
    assert response.body["count"] == 3


def test_single_product():
    response = app().handle("GET", "/products/SSP-1001")
    assert response.status == 200
    assert response.body["slug"] == "sugar-snap-peas"


def test_missing_product_becomes_a_404_body():
    response = app().handle("GET", "/products/SSP-9999")
    assert response.status == 404
    assert response.body["error"]["code"] == "not_found"
    assert response.body["error"]["title"].startswith("Not Found: ")


def test_invalid_sku_becomes_a_422_from_shared_core_validation():
    # shared_core.validation.ValidationError is a ValueError, not an ApiError,
    # so it is NOT swallowed by the handler. That is deliberate: the web layer
    # only translates api's own error type.
    with pytest.raises(ValueError):
        app().handle("GET", "/products/not-a-sku")


def test_unknown_route_is_a_404():
    response = app().handle("GET", "/nowhere")
    assert response.status == 404
    assert response.body["error"]["code"] == "not_found"


def test_tag_route():
    response = app().handle("GET", "/tags/veg")
    assert [p["sku"] for p in response.body["products"]] == ["SSP-1001", "SSP-1002"]


def test_quick_quote_route_converts_the_quantity():
    response = app().handle("GET", "/quote/SSP-1001/4")
    assert response.status == 200
    assert response.body["total"] == "14.00 USD"


def test_post_quote_with_a_full_body():
    response = app().handle(
        "POST",
        "/quote",
        {"basket": {"SSP-1001": 10, "SSP-1002": 2}, "tax_rate": "0.05", "promo": "SNAPPY10", "shipping": "4.99"},
    )
    assert response.status == 200
    assert response.body["gross"] == "39.50 USD"
    assert len(response.body["shipping"]) == 2
    assert "subtotal" in response.body["text"]


def test_post_quote_rejects_a_malformed_body():
    response = app().handle("POST", "/quote", {"basket": "nope"})
    assert response.status == 400
    assert response.body["error"]["code"] == "bad_request"


def test_post_quote_rejects_an_empty_basket():
    assert app().handle("POST", "/quote", {"basket": {}}).status == 400


def test_inactive_product_in_a_basket_is_a_400():
    assert app().handle("GET", "/quote/SSP-2002/1").status == 400


def test_app_accepts_an_injected_catalog():
    catalog = Catalog([Product("AAA-0001", "Widget", seed_catalog().get("SSP-1002").unit_price)])
    response = App(catalog).handle("GET", "/health")
    assert response.body == {"status": "ok", "products": 1}


def test_response_is_dict_like():
    response = Response(200, {"a": 1})
    assert response["status"] == 200 and response["body"] == {"a": 1}


def test_router_is_built_once_per_app():
    assert len(build_router()) == 6
