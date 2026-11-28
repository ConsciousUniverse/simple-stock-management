"""Defect: complete_transfer treats a JSON boolean cancel flag as a dispatch."""
from django.urls import reverse
from stock_manager.models import Item, TransferItem


def test_json_boolean_cancel_is_treated_as_cancel(manager_client, shop_user, make_item, app_config):
    """cancel=true sent as a JSON boolean must cancel the pending transfer, not dispatch it."""
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    body = {"sku": "A", "quantity": None, "shop_user_id": shop_user.username, "cancel": True}
    manager_client.post(reverse("complete_transfer"), body, format="json")
    assert Item.objects.get(sku="A").quantity == 10
    assert TransferItem.objects.count() == 0
