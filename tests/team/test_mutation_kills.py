"""
Member 1: tests added after the first mutmut run, to kill surviving mutants of
transfer_to_shop (missing tests and weak assertions). Each test names the mutants it targets.
"""
import pytest
from django.urls import reverse
from stock_manager import views
from stock_manager.models import Admin, Item, ShopItem, TransferItem

MAINT = "Transfers are disabled as the warehouse is being maintained. Please try again later."
ORDERED = ("This item has already been ordered and is awaiting dispatch. "
           "Please contact the warehouse manager if you wish to amend your order.")


def complete(client, sku, qty, username, cancel=None):
    body = {"sku": sku, "quantity": qty, "shop_user_id": username}
    if cancel is not None:
        body["cancel"] = cancel
    return client.post(reverse("complete_transfer"), body, format="json")


# mutants 6-9: maintenance message text
def test_locked_shop_user_cancel_gets_exact_maintenance_message(shop_client, shop_user, make_item):
    Admin.objects.create(id=1, edit_lock=True)
    item = make_item(sku="A")
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
    r = complete(shop_client, "A", None, shop_user.username, cancel="true")
    assert r.status_code == 400
    assert r.json()["detail"] == MAINT


# mutant 3: manager default must be False
def test_direct_call_default_manager_is_false_when_locked(shop_user, make_item):
    Admin.objects.create(id=1, edit_lock=True)
    item = make_item(sku="A", quantity=5)
    with pytest.raises(ValueError) as exc:
        views.transfer_to_shop(item, shop_user, 1)
    assert str(exc.value) == MAINT


# mutants 20, 21: zero-quantity message text
def test_direct_zero_quantity_exact_message(shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    with pytest.raises(ValueError) as exc:
        views.transfer_to_shop(item, shop_user, 0)
    assert str(exc.value) == "Transfer quantity must be greater than zero."


# mutants 24-27: not-enough-stock message text (request path)
def test_request_over_stock_exact_message(shop_client, make_item, app_config):
    make_item(sku="A", quantity=10)
    r = shop_client.post(reverse("transfer_item"), {"sku": "A", "transfer_quantity": 11}, format="json")
    assert r.status_code == 400
    assert r.json()["detail"] == "Not enough stock to transfer"


# mutants 34-37: already-ordered message text
def test_amend_after_order_exact_message(shop_client, make_item, app_config):
    make_item(sku="A", quantity=10)
    shop_client.post(reverse("transfer_item"), {"sku": "A", "transfer_quantity": 2}, format="json")
    shop_client.post(reverse("submit-transfer-request"))
    r = shop_client.post(reverse("transfer_item"), {"sku": "A", "transfer_quantity": 5}, format="json")
    assert r.status_code == 400
    assert r.json()["detail"] == ORDERED


# mutant 53: race-guard message text
def test_dispatch_race_guard_exact_message(shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=5)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=5, ordered=True)
    Item.objects.filter(sku="A").update(quantity=0)
    item.quantity = 5
    with pytest.raises(ValueError) as exc:
        views.transfer_to_shop(item, shop_user.id, 5, complete=True)
    assert str(exc.value) == "Not enough stock to transfer"


# mutant 13: cancel lookup must filter by item
def test_cancel_one_item_leaves_users_other_pending_item(manager_client, shop_user, make_item, app_config):
    a = make_item(sku="A")
    b = make_item(sku="B")
    TransferItem.objects.create(shop_user=shop_user, item=a, quantity=1, ordered=True)
    TransferItem.objects.create(shop_user=shop_user, item=b, quantity=1, ordered=True)
    r = complete(manager_client, "A", None, shop_user.username, cancel="true")
    assert r.status_code == 200
    assert not TransferItem.objects.filter(shop_user=shop_user, item=a).exists()
    assert TransferItem.objects.filter(shop_user=shop_user, item=b).exists()


# mutant 14: cancel lookup must filter by shop user
def test_cancel_for_one_user_leaves_other_users_pending_same_item(manager_client, shop_user, other_shop_user, make_item, app_config):
    a = make_item(sku="A")
    TransferItem.objects.create(shop_user=shop_user, item=a, quantity=1, ordered=True)
    TransferItem.objects.create(shop_user=other_shop_user, item=a, quantity=1, ordered=True)
    r = complete(manager_client, "A", None, shop_user.username, cancel="true")
    assert r.status_code == 200
    assert TransferItem.objects.filter(shop_user=other_shop_user, item=a).exists()
    assert not TransferItem.objects.filter(shop_user=shop_user, item=a).exists()


# mutant 45: dispatch must reduce only the dispatched item
def test_dispatch_reduces_only_the_dispatched_item(manager_client, shop_user, make_item, app_config):
    a = make_item(sku="A", quantity=10)
    b = make_item(sku="B", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=a, quantity=4, ordered=True)
    assert complete(manager_client, "A", 4, shop_user.username).status_code == 200
    assert Item.objects.get(sku="A").quantity == 6
    assert Item.objects.get(sku="B").quantity == 10


# mutant 69: dispatch must delete only that item's pending record
def test_dispatch_keeps_users_other_pending_item(manager_client, shop_user, make_item, app_config):
    a = make_item(sku="A", quantity=10)
    b = make_item(sku="B", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=a, quantity=2, ordered=True)
    TransferItem.objects.create(shop_user=shop_user, item=b, quantity=3, ordered=True)
    complete(manager_client, "A", 2, shop_user.username)
    assert TransferItem.objects.filter(shop_user=shop_user, item=b).exists()


# mutant 70: dispatch must delete only that user's pending record
def test_dispatch_keeps_other_users_pending_same_item(manager_client, shop_user, other_shop_user, make_item, app_config):
    a = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=a, quantity=2, ordered=True)
    TransferItem.objects.create(shop_user=other_shop_user, item=a, quantity=3, ordered=True)
    complete(manager_client, "A", 2, shop_user.username)
    assert TransferItem.objects.filter(shop_user=other_shop_user, item=a).exists()


# custom operator LIMIT_BOUNDARY in complete_transfer (quantity <= 0): quantity 0 must be
# rejected by the dispatch check itself, with the dispatch-specific message
def test_dispatch_zero_quantity_rejected_with_dispatch_message(manager_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    r = complete(manager_client, "A", 0, shop_user.username)
    assert r.status_code == 400
    assert r.json()["detail"] == "Quantity must be a positive integer."
    assert Item.objects.get(sku="A").quantity == 10


# custom operator LIMIT_BOUNDARY in transfer_item (quantity <= 0): the check runs before the
# item lookup, so quantity 0 for an unknown SKU is a 400 (rule), not a 404 (lookup)
def test_request_zero_quantity_checked_before_item_lookup(shop_client, app_config):
    r = shop_client.post(reverse("transfer_item"), {"sku": "NOPE", "transfer_quantity": 0}, format="json")
    assert r.status_code == 400
    assert r.json()["detail"] == "Transfer quantity must be greater than zero."
