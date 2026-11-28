"""Member 1: defensive branches of the transfer logic, reached with test doubles."""
from unittest import mock

import pytest
from django.urls import reverse
from stock_manager import views
from stock_manager.models import Item, TransferItem


def test_direct_zero_quantity_rejected(shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    with pytest.raises(ValueError, match="greater than zero"):
        views.transfer_to_shop(item, shop_user, 0)


def test_dispatch_race_guard_rejects_when_stock_vanished(shop_user, make_item, app_config):
    """Stock check passes on the stale object, but the conditional UPDATE finds no row."""
    item = make_item(sku="A", quantity=5)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=5, ordered=True)
    Item.objects.filter(sku="A").update(quantity=0)  # concurrent dispatch drained stock
    item.quantity = 5  # stale in-memory value
    with pytest.raises(ValueError, match="Not enough stock"):
        views.transfer_to_shop(item, shop_user.id, 5, complete=True)
    assert Item.objects.get(sku="A").quantity == 0


def test_transfer_unexpected_error_hidden_from_client(shop_client, make_item, app_config):
    make_item(sku="A")
    with mock.patch.object(views, "transfer_to_shop", side_effect=RuntimeError("secret db detail")):
        r = shop_client.post(reverse("transfer_item"), {"sku": "A", "transfer_quantity": 1}, format="json")
    assert r.status_code == 400
    assert "secret" not in r.json()["detail"]


def test_submit_unexpected_error_leaves_state_unchanged(shop_client, shop_user, make_item, app_config):
    item = make_item(sku="A")
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
    with mock.patch.object(views, "SendEmail") as email:
        email.return_value.compose.side_effect = RuntimeError("smtp down")
        r = shop_client.post(reverse("submit-transfer-request"))
    assert r.status_code == 400
    assert "smtp" not in r.json()["detail"]
    assert TransferItem.objects.get().ordered is False