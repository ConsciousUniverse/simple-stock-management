from decimal import Decimal

import pytest

from stock_manager.models import Item

pytestmark = pytest.mark.django_db


def result_skus(response):
    return [row["sku"] for row in response.json()["results"]]


class TestItemListAccess:
    def test_anonymous_denied(self, api_client):
        assert api_client.get("/api/items/").status_code == 403

    def test_authenticated_allowed(self, shop_client, make_item):
        make_item()
        response = shop_client.get("/api/items/")
        assert response.status_code == 200
        assert result_skus(response) == ["SKU-1"]


class TestItemListFiltering:
    def test_inactive_items_excluded(self, manager_client, make_item):
        make_item(sku="LIVE")
        make_item(sku="DEAD", is_active=False)
        assert result_skus(manager_client.get("/api/items/")) == ["LIVE"]

    def test_search_matches_sku_and_description(self, manager_client, make_item):
        make_item(sku="ABC-1", description="Bird feeder")
        make_item(sku="XYZ-2", description="Bag of seed")
        make_item(sku="XYZ-3", description="Dog lead")

        assert result_skus(manager_client.get("/api/items/?search=abc")) == ["ABC-1"]
        assert result_skus(manager_client.get("/api/items/?search=seed")) == ["XYZ-2"]
        assert result_skus(manager_client.get("/api/items/?search=nomatch")) == []

    def test_default_ordering_is_most_recently_updated_first(
        self, manager_client, make_item
    ):
        make_item(sku="FIRST")
        make_item(sku="SECOND")
        assert result_skus(manager_client.get("/api/items/")) == ["SECOND", "FIRST"]


class TestItemListOrdering:
    def test_sku_uses_natural_sort(self, manager_client, make_item):
        for sku in ("SKU10", "SKU2", "SKU1"):
            make_item(sku=sku)
        response = manager_client.get("/api/items/?ordering=sku")
        assert result_skus(response) == ["SKU1", "SKU2", "SKU10"]

    def test_sku_natural_sort_descending(self, manager_client, make_item):
        for sku in ("SKU10", "SKU2", "SKU1"):
            make_item(sku=sku)
        response = manager_client.get("/api/items/?ordering=-sku")
        assert result_skus(response) == ["SKU10", "SKU2", "SKU1"]

    def test_quantity_sorted_numerically(self, manager_client, make_item):
        make_item(sku="A", quantity=10)
        make_item(sku="B", quantity=2)
        make_item(sku="C", quantity=9)
        response = manager_client.get("/api/items/?ordering=quantity")
        assert result_skus(response) == ["B", "C", "A"]
        response = manager_client.get("/api/items/?ordering=-quantity")
        assert result_skus(response) == ["A", "C", "B"]

    def test_description_sorted_case_insensitively(self, manager_client, make_item):
        make_item(sku="A", description="banana")
        make_item(sku="B", description="Apple")
        make_item(sku="C", description="cherry")
        response = manager_client.get("/api/items/?ordering=description")
        assert result_skus(response) == ["B", "A", "C"]


class TestItemCreate:
    def test_create_new_item(self, manager_client):
        response = manager_client.post(
            "/api/items/",
            {"sku": "NEW-1", "description": "Widget", "retail_price": "9.99", "quantity": 5},
            format="json",
        )
        assert response.status_code == 201
        item = Item.objects.get(sku="NEW-1")
        assert item.retail_price == Decimal("9.99")
        assert item.quantity == 5
        assert item.is_active is True

    def test_duplicate_active_sku_rejected(self, manager_client, make_item):
        make_item(sku="DUP")
        response = manager_client.post(
            "/api/items/",
            {"sku": "DUP", "description": "x", "retail_price": "1.00", "quantity": 1},
            format="json",
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_creating_inactive_sku_reactivates_it(self, manager_client, make_item):
        make_item(sku="GHOST", description="old", quantity=0, is_active=False)
        response = manager_client.post(
            "/api/items/",
            {"sku": "GHOST", "description": "new", "retail_price": "2.50", "quantity": 3},
            format="json",
        )
        assert response.status_code == 200
        item = Item.objects.get(sku="GHOST")
        assert item.is_active is True
        assert item.description == "new"
        assert item.quantity == 3

    def test_invalid_payload_rejected(self, manager_client):
        response = manager_client.post(
            "/api/items/",
            {"sku": "BAD", "description": "x", "retail_price": "9.999", "quantity": 1},
            format="json",
        )
        assert response.status_code == 400


class TestItemUpdate:
    def test_non_manager_denied(self, shop_client, make_item):
        make_item()
        response = shop_client.put(
            "/api/items/SKU-1/",
            {"sku": "SKU-1", "quantity": 99},
            format="json",
        )
        assert response.status_code == 403

    def test_manager_can_update_fields(self, manager_client, make_item):
        make_item(sku="UPD", quantity=1, retail_price="1.00")
        response = manager_client.put(
            "/api/items/UPD/",
            {"sku": "UPD", "quantity": 42, "retail_price": "3.75"},
            format="json",
        )
        assert response.status_code == 200
        item = Item.objects.get(sku="UPD")
        assert item.quantity == 42
        assert item.retail_price == Decimal("3.75")

    def test_updating_inactive_item_reactivates_it(self, manager_client, make_item):
        make_item(sku="OLD", is_active=False)
        response = manager_client.put(
            "/api/items/OLD/",
            {"sku": "OLD", "description": "revived"},
            format="json",
        )
        assert response.status_code == 200
        item = Item.objects.get(sku="OLD")
        assert item.is_active is True
        assert item.description == "revived"

    def test_unknown_sku_returns_404(self, manager_client):
        response = manager_client.put(
            "/api/items/NOPE/",
            {"sku": "NOPE", "quantity": 1},
            format="json",
        )
        assert response.status_code == 404

    def test_invalid_price_rejected(self, manager_client, make_item):
        make_item(sku="UPD")
        response = manager_client.put(
            "/api/items/UPD/",
            {"sku": "UPD", "retail_price": "not-a-price"},
            format="json",
        )
        assert response.status_code == 400


class TestItemDestroy:
    def test_non_manager_denied(self, shop_client, make_item):
        make_item()
        assert shop_client.delete("/api/items/SKU-1/").status_code == 403
        assert Item.objects.get(sku="SKU-1").is_active is True

    def test_manager_soft_deletes(self, manager_client, make_item):
        make_item(sku="DEL")
        response = manager_client.delete("/api/items/DEL/")
        assert response.status_code == 204
        # Soft delete: row remains but is deactivated.
        item = Item.objects.get(sku="DEL")
        assert item.is_active is False

    def test_unknown_sku_returns_404(self, manager_client):
        assert manager_client.delete("/api/items/NOPE/").status_code == 404
