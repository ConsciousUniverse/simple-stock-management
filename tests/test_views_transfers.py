import pytest

from stock_manager.models import Item, ShopItem, TransferItem

pytestmark = pytest.mark.django_db


class TestTransferItemEndpoint:
    """POST /api/transfer/ — a shop user requests stock from the warehouse."""

    def test_anonymous_denied(self, api_client, app_config):
        assert api_client.post("/api/transfer/", {}, format="json").status_code == 403

    def test_denied_during_maintenance(self, shop_client, app_config, make_item):
        app_config.edit_lock = True
        app_config.save()
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": "1"},
            format="json",
        )
        assert response.status_code == 403
        assert "maintained" in response.json()["detail"]

    def test_non_shop_user_denied(self, manager_client, app_config, make_item):
        make_item()
        response = manager_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": "1"},
            format="json",
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("bad_quantity", ["abc", "1.5", None])
    def test_non_integer_quantity_rejected(
        self, shop_client, app_config, make_item, bad_quantity
    ):
        make_item()
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": bad_quantity},
            format="json",
        )
        assert response.status_code == 400
        assert "must be an integer" in response.json()["detail"]

    def test_missing_quantity_rejected(self, shop_client, app_config, make_item):
        make_item()
        response = shop_client.post(
            "/api/transfer/", {"sku": "SKU-1"}, format="json"
        )
        assert response.status_code == 400
        assert "must be an integer" in response.json()["detail"]

    @pytest.mark.parametrize("bad_quantity", ["0", "-3", 0, -3])
    def test_non_positive_quantity_rejected(
        self, shop_client, app_config, make_item, bad_quantity
    ):
        make_item()
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": bad_quantity},
            format="json",
        )
        assert response.status_code == 400
        assert "greater than zero" in response.json()["detail"]

    def test_quantity_accepted_as_json_number(
        self, shop_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": 3},
            format="json",
        )
        assert response.status_code == 200
        transfer = TransferItem.objects.get(shop_user=shop_user, item=item)
        assert transfer.quantity == 3

    def test_works_without_admin_config_row(
        self, shop_client, shop_user, make_item, db
    ):
        # A fresh install has no Admin row; transfers must still work.
        item = make_item(quantity=10)
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": "3"},
            format="json",
        )
        assert response.status_code == 200
        assert TransferItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_unknown_sku_returns_404(self, shop_client, app_config):
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "NOPE", "transfer_quantity": "1"},
            format="json",
        )
        assert response.status_code == 404

    def test_insufficient_stock_rejected(self, shop_client, app_config, make_item):
        make_item(quantity=2)
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": "3"},
            format="json",
        )
        assert response.status_code == 400
        assert "Not enough stock" in response.json()["detail"]

    def test_successful_request_creates_pending_transfer(
        self, shop_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": "3"},
            format="json",
        )
        assert response.status_code == 200
        transfer = TransferItem.objects.get(shop_user=shop_user, item=item)
        assert transfer.quantity == 3
        assert transfer.ordered is False
        # Warehouse stock is untouched until the manager dispatches.
        item.refresh_from_db()
        assert item.quantity == 10

    def test_repeat_request_amends_pending_quantity(
        self, shop_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        for quantity in ("3", "5"):
            shop_client.post(
                "/api/transfer/",
                {"sku": "SKU-1", "transfer_quantity": quantity},
                format="json",
            )
        transfers = TransferItem.objects.filter(shop_user=shop_user, item=item)
        assert transfers.count() == 1
        assert transfers.get().quantity == 5

    def test_already_ordered_item_cannot_be_amended(
        self, shop_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=2, ordered=True
        )
        response = shop_client.post(
            "/api/transfer/",
            {"sku": "SKU-1", "transfer_quantity": "4"},
            format="json",
        )
        assert response.status_code == 400
        assert "already been ordered" in response.json()["detail"]


class TestSubmitTransferRequest:
    """POST /api/submit-transfer-request/ — locks in all pending transfers."""

    def test_anonymous_denied(self, api_client, app_config):
        response = api_client.post("/api/submit-transfer-request/", {}, format="json")
        assert response.status_code == 403

    def test_no_pending_items_rejected(self, shop_client, app_config):
        response = shop_client.post("/api/submit-transfer-request/", {}, format="json")
        assert response.status_code == 400
        assert "no outstanding items" in response.json()["detail"]

    def test_denied_during_maintenance(
        self, shop_client, shop_user, app_config, make_item
    ):
        app_config.edit_lock = True
        app_config.save()
        TransferItem.objects.create(shop_user=shop_user, item=make_item(), quantity=1)
        response = shop_client.post("/api/submit-transfer-request/", {}, format="json")
        assert response.status_code == 403

    def test_marks_pending_transfers_as_ordered(
        self, shop_client, shop_user, app_config, make_item
    ):
        pending = TransferItem.objects.create(
            shop_user=shop_user, item=make_item(), quantity=2
        )
        response = shop_client.post("/api/submit-transfer-request/", {}, format="json")
        assert response.status_code == 200
        pending.refresh_from_db()
        assert pending.ordered is True

    def test_works_without_admin_config_row(self, shop_client, shop_user, make_item, db):
        # A fresh install has no Admin row; submitting must still work.
        pending = TransferItem.objects.create(
            shop_user=shop_user, item=make_item(), quantity=2
        )
        response = shop_client.post("/api/submit-transfer-request/", {}, format="json")
        assert response.status_code == 200
        pending.refresh_from_db()
        assert pending.ordered is True

    def test_does_not_touch_other_users_pending_transfers(
        self, shop_client, shop_user, other_shop_user, app_config, make_item
    ):
        other_pending = TransferItem.objects.create(
            shop_user=other_shop_user, item=make_item(sku="OTHER"), quantity=1
        )
        TransferItem.objects.create(
            shop_user=shop_user, item=make_item(sku="MINE"), quantity=1
        )
        shop_client.post("/api/submit-transfer-request/", {}, format="json")
        other_pending.refresh_from_db()
        assert other_pending.ordered is False

    def test_sends_notification_email_when_enabled(
        self, shop_client, shop_user, groups, app_config, make_item, mailoutbox
    ):
        from django.contrib.auth.models import User

        recipient = User.objects.create_user(
            username="warehouse", password="x", email="warehouse@example.com"
        )
        recipient.groups.add(groups["receive_mail"])
        app_config.allow_email_notifications = True
        app_config.save()
        TransferItem.objects.create(
            shop_user=shop_user, item=make_item(sku="SKU-9"), quantity=2
        )

        response = shop_client.post("/api/submit-transfer-request/", {}, format="json")

        assert response.status_code == 200
        assert len(mailoutbox) == 1
        message = mailoutbox[0]
        assert message.to == ["warehouse@example.com"]
        assert "SKU-9" in message.body

    def test_no_email_sent_when_notifications_disabled(
        self, shop_client, shop_user, groups, app_config, make_item, mailoutbox
    ):
        from django.contrib.auth.models import User

        recipient = User.objects.create_user(
            username="warehouse", password="x", email="warehouse@example.com"
        )
        recipient.groups.add(groups["receive_mail"])
        TransferItem.objects.create(shop_user=shop_user, item=make_item(), quantity=2)

        response = shop_client.post("/api/submit-transfer-request/", {}, format="json")

        assert response.status_code == 200
        assert len(mailoutbox) == 0


class TestCompleteTransfer:
    """POST /api/complete-transfer/ — manager dispatch or cancellation."""

    @staticmethod
    def payload(sku="SKU-1", quantity=4, shop_user_id="shop1", cancel="false"):
        return {
            "sku": sku,
            "quantity": quantity,
            "shop_user_id": shop_user_id,
            "cancel": cancel,
        }

    def test_unknown_shop_user_rejected(self, manager_client, app_config):
        response = manager_client.post(
            "/api/complete-transfer/",
            self.payload(shop_user_id="ghost"),
            format="json",
        )
        assert response.status_code == 400
        assert "Shop user not found" in response.json()["detail"]

    def test_non_manager_cannot_dispatch(
        self, shop_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = shop_client.post(
            "/api/complete-transfer/", self.payload(), format="json"
        )
        assert response.status_code == 403

    def test_manager_dispatch_moves_stock(
        self, manager_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )

        response = manager_client.post(
            "/api/complete-transfer/", self.payload(quantity=4), format="json"
        )

        assert response.status_code == 200
        item.refresh_from_db()
        assert item.quantity == 6
        shop_item = ShopItem.objects.get(shop_user=shop_user, item=item)
        assert shop_item.quantity == 4
        assert not TransferItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_dispatch_rejects_negative_quantity(
        self, manager_client, shop_user, app_config, make_item
    ):
        # A negative dispatch quantity would otherwise *inflate* warehouse
        # stock and reduce shop stock.
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(quantity=-5), format="json"
        )
        assert response.status_code == 400
        item.refresh_from_db()
        assert item.quantity == 10
        assert not ShopItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_dispatch_rejects_zero_quantity(
        self, manager_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(quantity=0), format="json"
        )
        assert response.status_code == 400
        item.refresh_from_db()
        assert item.quantity == 10

    def test_dispatch_rejects_non_integer_quantity(
        self, manager_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(quantity="abc"), format="json"
        )
        assert response.status_code == 400
        assert "integer" in response.json()["detail"].lower()
        item.refresh_from_db()
        assert item.quantity == 10

    def test_dispatch_accumulates_existing_shop_stock(
        self, manager_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=2)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )

        manager_client.post(
            "/api/complete-transfer/", self.payload(quantity=4), format="json"
        )

        shop_item = ShopItem.objects.get(shop_user=shop_user, item=item)
        assert shop_item.quantity == 6

    def test_dispatch_more_than_stock_rejected(
        self, manager_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=3)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(quantity=4), format="json"
        )
        assert response.status_code == 400
        assert "Not enough stock" in response.json()["detail"]
        item.refresh_from_db()
        assert item.quantity == 3

    def test_unknown_sku_returns_404(self, manager_client, shop_user, app_config):
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(sku="NOPE"), format="json"
        )
        assert response.status_code == 404

    def test_shop_user_can_cancel_own_pending_transfer(
        self, shop_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4)

        response = shop_client.post(
            "/api/complete-transfer/", self.payload(cancel="true"), format="json"
        )

        assert response.status_code == 200
        assert not TransferItem.objects.filter(shop_user=shop_user, item=item).exists()
        # Cancelling never moves stock.
        item.refresh_from_db()
        assert item.quantity == 10
        assert not ShopItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_manager_can_cancel_submitted_transfer(
        self, manager_client, shop_user, app_config, make_item
    ):
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(cancel="true"), format="json"
        )
        assert response.status_code == 200
        assert not TransferItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_cancel_of_nonexistent_transfer_rejected(
        self, manager_client, shop_user, app_config, make_item
    ):
        make_item(quantity=10)
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(cancel="true"), format="json"
        )
        assert response.status_code == 400

    def test_manager_can_dispatch_during_maintenance(
        self, manager_client, shop_user, app_config, make_item
    ):
        app_config.edit_lock = True
        app_config.save()
        item = make_item(quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        response = manager_client.post(
            "/api/complete-transfer/", self.payload(quantity=4), format="json"
        )
        assert response.status_code == 200
        item.refresh_from_db()
        assert item.quantity == 6

    def test_shop_user_cannot_cancel_during_maintenance(
        self, shop_client, shop_user, app_config, make_item
    ):
        app_config.edit_lock = True
        app_config.save()
        item = make_item(quantity=10)
        TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4)
        response = shop_client.post(
            "/api/complete-transfer/", self.payload(cancel="true"), format="json"
        )
        assert response.status_code == 400
        assert TransferItem.objects.filter(shop_user=shop_user, item=item).exists()
