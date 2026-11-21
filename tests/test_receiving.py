"""Goods receipts (stock in against a supplier PO) and issuing to a site."""

import pytest

from stock_manager.models import Admin, GoodsReceipt, GoodsReceiptLine, Item, ShopItem

pytestmark = pytest.mark.django_db


def receive(client, **payload):
    body = {"po_number": "PO-2026-000123", "supplier": "Elsewedy Cables", "lines": []}
    body.update(payload)
    return client.post("/api/receiving/", body, format="json")


class TestReceiving:
    def test_requires_authentication(self, api_client):
        response = api_client.post("/api/receiving/", {"po_number": "PO-1"}, format="json")
        assert response.status_code in (401, 403)

    def test_books_the_delivery_and_increases_stock(
        self, manager_client, app_config, make_item
    ):
        item = make_item(sku="NSCOM-1001", quantity=10)

        response = receive(
            manager_client,
            lines=[{"sku": "NSCOM-1001", "quantity": 15, "description": "Breaker"}],
        )

        assert response.status_code == 201
        item.refresh_from_db()
        assert item.quantity == 25
        receipt = GoodsReceipt.objects.get()
        assert receipt.po_number == "PO-2026-000123"
        assert receipt.supplier == "Elsewedy Cables"
        assert receipt.received_by == manager_client.handler._force_user
        assert receipt.total_quantity == 15
        assert response.data["lines"][0]["warehouse_quantity"] == 25

    def test_creates_an_unknown_item_so_a_new_code_can_arrive(
        self, manager_client, app_config
    ):
        response = receive(
            manager_client,
            lines=[{"sku": "NEW-1", "quantity": 4, "description": "New part"}],
        )

        assert response.status_code == 201
        item = Item.objects.get(sku="NEW-1")
        assert item.quantity == 4
        assert item.description == "New part"

    def test_same_po_can_arrive_in_several_shipments(
        self, manager_client, app_config, make_item
    ):
        item = make_item(sku="NSCOM-1001", quantity=0)

        receive(manager_client, lines=[{"sku": "NSCOM-1001", "quantity": 5}])
        receive(manager_client, lines=[{"sku": "NSCOM-1001", "quantity": 7}])

        item.refresh_from_db()
        assert item.quantity == 12
        assert GoodsReceipt.objects.count() == 2
        assert GoodsReceiptLine.objects.count() == 2

    def test_a_repeated_sku_in_one_delivery_is_summed(
        self, manager_client, app_config, make_item
    ):
        item = make_item(sku="NSCOM-1001", quantity=0)

        receive(
            manager_client,
            lines=[
                {"sku": "NSCOM-1001", "quantity": 3},
                {"sku": "NSCOM-1001", "quantity": 4},
            ],
        )

        item.refresh_from_db()
        assert item.quantity == 7
        assert GoodsReceiptLine.objects.count() == 1

    def test_po_number_is_required(self, manager_client, app_config):
        response = receive(manager_client, po_number="", lines=[{"sku": "A", "quantity": 1}])

        assert response.status_code == 400
        assert "purchase order" in str(response.data["detail"]).lower()
        assert GoodsReceipt.objects.count() == 0

    @pytest.mark.parametrize("quantity", [0, -3, "abc", None])
    def test_quantity_must_be_a_positive_integer(self, manager_client, app_config, quantity):
        response = receive(
            manager_client, lines=[{"sku": "A", "quantity": quantity}]
        )

        assert response.status_code == 400
        assert Item.objects.count() == 0

    def test_a_delivery_without_items_is_rejected(self, manager_client, app_config):
        response = receive(manager_client, lines=[{"sku": "", "quantity": 2}])

        assert response.status_code == 400
        assert GoodsReceipt.objects.count() == 0

    def test_receiving_is_blocked_in_maintenance_mode(self, manager_client, app_config):
        Admin.objects.filter(pk=app_config.pk).update(edit_lock=True)

        response = receive(manager_client, lines=[{"sku": "A", "quantity": 1}])

        assert response.status_code == 403
        assert GoodsReceipt.objects.count() == 0

    def test_lists_receipts_newest_first(self, manager_client, app_config, make_item):
        make_item(sku="NSCOM-1001", quantity=0)
        receive(manager_client, po_number="PO-1", lines=[{"sku": "NSCOM-1001", "quantity": 2}])
        receive(manager_client, po_number="PO-2", lines=[{"sku": "NSCOM-1001", "quantity": 3}])

        response = manager_client.get("/api/receipts/")

        assert response.status_code == 200
        assert [row["po_number"] for row in response.data["results"]] == ["PO-2", "PO-1"]
        assert response.data["results"][0]["total_quantity"] == 3
        assert response.data["results"][0]["lines"][0]["sku"] == "NSCOM-1001"


class TestIssueToSite:
    def test_moves_stock_to_the_site(self, manager_client, app_config, make_item, shop_user):
        item = make_item(sku="NSCOM-1001", quantity=10)

        response = manager_client.post(
            "/api/issue/", {"sku": "NSCOM-1001", "site_id": shop_user.id, "quantity": 4}, format="json"
        )

        assert response.status_code == 200
        item.refresh_from_db()
        assert item.quantity == 6
        assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 4

    def test_only_a_manager_can_issue(self, shop_client, app_config, make_item, shop_user):
        make_item(sku="NSCOM-1001", quantity=10)

        response = shop_client.post(
            "/api/issue/", {"sku": "NSCOM-1001", "site_id": shop_user.id, "quantity": 1}, format="json"
        )

        assert response.status_code == 403

    def test_refuses_more_than_the_warehouse_holds(self, manager_client, app_config, make_item, shop_user):
        item = make_item(sku="NSCOM-1001", quantity=2)

        response = manager_client.post(
            "/api/issue/", {"sku": "NSCOM-1001", "site_id": shop_user.id, "quantity": 5}, format="json"
        )

        assert response.status_code == 400
        item.refresh_from_db()
        assert item.quantity == 2

    def test_unknown_site_is_rejected(self, manager_client, app_config, make_item):
        make_item(sku="NSCOM-1001", quantity=10)

        response = manager_client.post(
            "/api/issue/", {"sku": "NSCOM-1001", "site_id": 9999, "quantity": 1}, format="json"
        )

        assert response.status_code == 400

    def test_sites_endpoint_lists_site_accounts(self, manager_client, shop_user, plain_user):
        response = manager_client.get("/api/sites/")

        assert response.status_code == 200
        usernames = [row["username"] for row in response.data["results"]]
        assert usernames == ["shop1"]
