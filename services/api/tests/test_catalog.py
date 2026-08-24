"""api.catalog tests — exercise shared-core money/validation/ids in-process."""

import pytest

from api.catalog import Catalog, Product, seed_catalog
from api.errors import Conflict, NotFound
from shared_core.money import Money
from shared_core.validation import ValidationError


def test_product_normalises_sku_and_tags():
    product = Product("ssp-1001", "Sugar Snap Peas", Money.of("3.50", "USD"), tags=(" Veg", "veg", "FRESH"))
    assert product.sku == "SSP-1001"
    assert product.tags == ("fresh", "veg")
    assert product.slug == "sugar-snap-peas"
    assert product.has_tag(" VEG ")


def test_product_rejects_bad_sku():
    with pytest.raises(ValidationError):
        Product("nope", "X", Money.of("1", "USD"))


def test_catalog_add_get_and_membership():
    catalog = Catalog()
    catalog.add(Product("SSP-1001", "Peas", Money.of("3.50", "USD")))
    assert len(catalog) == 1
    assert "ssp-1001" in catalog
    assert "SSP-9999" not in catalog
    assert "garbage" not in catalog
    assert catalog.get("ssp-1001").name == "Peas"


def test_catalog_rejects_duplicates_and_missing():
    catalog = seed_catalog()
    with pytest.raises(Conflict):
        catalog.add(Product("SSP-1001", "Dupe", Money.of("1.00", "USD")))
    with pytest.raises(NotFound) as exc:
        catalog.get("SSP-9999")
    assert exc.value.detail == {"sku": "SSP-9999"}


def test_seed_catalog_lists_only_active_products_in_sku_order():
    catalog = seed_catalog()
    assert len(catalog) == 4
    assert [p.sku for p in catalog.list_active()] == ["SSP-1001", "SSP-1002", "SSP-2001"]


def test_search_by_tag():
    catalog = seed_catalog()
    assert [p.sku for p in catalog.search_by_tag("VEG")] == ["SSP-1001", "SSP-1002"]
    assert [p.sku for p in catalog.search_by_tag("pantry")] == ["SSP-2001"]
    assert catalog.search_by_tag("nope") == []


def test_reprice_returns_a_new_product():
    catalog = seed_catalog()
    updated = catalog.reprice("SSP-1001", Money.of("4.00", "USD"))
    assert updated.unit_price == Money.of("4.00", "USD")
    assert catalog.get("SSP-1001").unit_price == Money.of("4.00", "USD")
    assert updated.tags == ("fresh", "veg")


def test_reprice_guards_currency_and_sign():
    catalog = seed_catalog()
    with pytest.raises(Conflict):
        catalog.reprice("SSP-1001", Money.of("4.00", "EUR"))
    with pytest.raises(Conflict):
        catalog.reprice("SSP-1001", Money.of("-1.00", "USD"))


def test_deactivate_removes_from_active_listing():
    catalog = seed_catalog()
    catalog.deactivate("SSP-1002")
    assert [p.sku for p in catalog.list_active()] == ["SSP-1001", "SSP-2001"]


def test_catalogue_value_sums_active_prices():
    catalog = seed_catalog()
    assert catalog.catalogue_value() == Money.of("24.74", "USD")
    assert Catalog().catalogue_value() == Money.zero("USD")
