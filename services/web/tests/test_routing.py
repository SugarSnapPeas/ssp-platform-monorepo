"""Pure web tests: no api, no shared-core. The web lane's control case."""

import pytest

from web.routing import DuplicateRoute, NoRoute, Route, RouteMatch, Router


def router():
    return (
        Router()
        .add("GET", "/health", "health")
        .add("GET", "/products", "products")
        .add("GET", "/products/:sku", "product")
        .add("GET", "/quote/:sku/:quantity:int", "quick_quote")
        .add("POST", "/quote", "quote")
    )


def test_static_routes():
    assert router().resolve("GET", "/health") == RouteMatch("health", {})
    assert router().resolve("get", "/products/") == RouteMatch("products", {})


def test_string_capture():
    assert router().resolve("GET", "/products/SSP-1001") == RouteMatch(
        "product", {"sku": "SSP-1001"}
    )


def test_int_capture_is_converted():
    match = router().resolve("GET", "/quote/SSP-1001/12")
    assert match == RouteMatch("quick_quote", {"sku": "SSP-1001", "quantity": 12})
    assert isinstance(match.params["quantity"], int)


def test_int_capture_rejects_non_digits():
    with pytest.raises(NoRoute):
        router().resolve("GET", "/quote/SSP-1001/many")


def test_method_is_part_of_the_match():
    assert router().resolve("POST", "/quote").name == "quote"
    with pytest.raises(NoRoute):
        router().resolve("DELETE", "/quote")


@pytest.mark.parametrize("path", ["/nope", "/products/a/b", "/", "/quote/only-sku"])
def test_unmatched_paths_raise(path):
    with pytest.raises(NoRoute):
        router().resolve("GET", path)


def test_duplicate_registration_is_rejected():
    with pytest.raises(DuplicateRoute):
        router().add("get", "/health/", "health-again")


def test_pattern_must_be_absolute():
    with pytest.raises(ValueError):
        Route("GET", "health", "health")


def test_first_registered_wins():
    r = Router().add("GET", "/products/new", "static").add("GET", "/products/:sku", "dynamic")
    assert r.resolve("GET", "/products/new").name == "static"
    assert r.resolve("GET", "/products/SSP-1001").name == "dynamic"


def test_allowed_methods_and_len():
    r = router()
    assert len(r) == 5
    # only POST is registered on /quote; the GET quote route is 3 segments long
    assert r.allowed_methods("/quote") == ["POST"]
    assert r.allowed_methods("/products/SSP-1001") == ["GET"]
    assert r.allowed_methods("/nope/at/all") == []


def test_allowed_methods_reports_every_method_on_a_shared_pattern():
    r = (
        Router()
        .add("GET", "/basket", "show")
        .add("POST", "/basket", "create")
        .add("DELETE", "/basket", "clear")
    )
    assert r.allowed_methods("/basket") == ["DELETE", "GET", "POST"]
