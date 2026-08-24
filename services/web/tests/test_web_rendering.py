"""In-process end-to-end rendering test for the web lane.

Always selected via ``test-selection-rules`` in
``services/web/.circleci/test-suites.yml``.
"""

from api.catalog import Catalog, Product, seed_catalog
from web.app import App
from web.views import quote_view, render_quote_text


def test_quote_page_renders_top_to_bottom():
    response = App().handle(
        "POST", "/quote", {"basket": {"SSP-1001": 3, "SSP-2001": 1}, "tax_rate": "0.10"}
    )
    assert response.status == 200
    lines = response.body["text"].splitlines()
    assert lines == [
        "3 x Sugar Snap Peas @ 3.50 USD = 10.50 USD",
        "1 x Pea Protein Powder @ 18.99 USD = 18.99 USD",
        "subtotal 29.49 USD / discount 0.00 USD / tax 2.95 USD / total 32.44 USD",
    ]


def test_rendered_output_is_html_escaped():
    unit_price = seed_catalog().get("SSP-1001").unit_price
    catalog = Catalog([Product("SSP-1001", "<script>Peas</script>", unit_price)])
    text = render_quote_text(quote_view(catalog, {"SSP-1001": 1}))
    assert "<script>" not in text
    assert "&lt;script&gt;Peas&lt;/script&gt;" in text


def test_every_route_in_the_default_app_responds():
    application = App()
    probes = [
        ("GET", "/health", None),
        ("GET", "/products", None),
        ("GET", "/products/SSP-1001", None),
        ("GET", "/tags/veg", None),
        ("GET", "/quote/SSP-1001/2", None),
        ("POST", "/quote", {"basket": {"SSP-1001": 1}}),
    ]
    statuses = [application.handle(m, p, b).status for m, p, b in probes]
    assert statuses == [200] * len(probes)


def test_catalog_page_and_quote_page_agree_on_prices():
    application = App()
    listing = application.handle("GET", "/products").body
    unit = {p["sku"]: p["unit_price"] for p in listing["products"]}
    quoted = application.handle("GET", "/quote/SSP-2001/1").body
    assert quoted["lines"][0]["unit_price"] == unit["SSP-2001"]
    assert quoted["total"] == unit["SSP-2001"]
