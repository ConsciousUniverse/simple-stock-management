"""
Member 1 team tests: server-side transfer business rules.
Rules: R1 quantity boundary, R2 maintenance-mode decision,
       R3 transfer state change, R4 role permissions.
Fixtures come from tests/conftest.py (shared, not upstream test code).
"""
import pytest
from django.urls import reverse
from stock_manager.models import Admin, Item, ShopItem, TransferItem

TRANSFER = "transfer_item"
COMPLETE = "complete_transfer"
SUBMIT = "submit-transfer-request"


def post_transfer(client, sku, qty):
    return client.post(reverse(TRANSFER), {"sku": sku, "transfer_quantity": qty}, format="json")


def post_complete(client, sku, qty, shop_username, cancel=None):
    body = {"sku": sku, "quantity": qty, "shop_user_id": shop_username}
    if cancel is not None:
        body["cancel"] = cancel
    return client.post(reverse(COMPLETE), body, format="json")


# ---------- R1: quantity boundary (stock = 10) ----------
@pytest.mark.parametrize("qty,expected", [
    (0, 400), (1, 200), (9, 200), (10, 200), (11, 400),
])
def test_R1_boundary_request_quantity(shop_client, shop_user, make_item, app_config, qty, expected):
    make_item(sku="A", quantity=10)
    r = post_transfer(shop_client, "A", qty)
    assert r.status_code == expected
    assert TransferItem.objects.filter(shop_user=shop_user, item_id="A").exists() == (expected == 200)


def test_R1_negative_and_non_integer_rejected(shop_client, make_item, app_config):
    make_item(sku="A", quantity=10)
    assert post_transfer(shop_client, "A", -3).status_code == 400
    assert post_transfer(shop_client, "A", "abc").status_code == 400
    assert post_transfer(shop_client, "A", None).status_code == 400
    assert TransferItem.objects.count() == 0


def test_R1_unknown_sku_404(shop_client, app_config):
    assert post_transfer(shop_client, "NOPE", 1).status_code == 404


def test_R1_request_does_not_change_stock(shop_client, make_item, app_config):
    make_item(sku="A", quantity=10)
    post_transfer(shop_client, "A", 4)
    assert Item.objects.get(sku="A").quantity == 10


# ---------- R2: maintenance mode decision (edit_lock) ----------
def test_R2_locked_blocks_shop_user_transfer(shop_client, make_item):
    Admin.objects.create(id=1, edit_lock=True)
    make_item(sku="A", quantity=10)
    r = post_transfer(shop_client, "A", 1)
    assert r.status_code == 403
    assert TransferItem.objects.count() == 0


def test_R2_locked_blocks_submit(shop_client, shop_user, make_item):
    Admin.objects.create(id=1, edit_lock=True)
    item = make_item(sku="A")
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
    assert shop_client.post(reverse(SUBMIT)).status_code == 403
    assert TransferItem.objects.get().ordered is False


def test_R2_locked_manager_can_still_dispatch(manager_client, shop_user, make_item):
    Admin.objects.create(id=1, edit_lock=True)
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=3, ordered=True)
    r = post_complete(manager_client, "A", 3, shop_user.username)
    assert r.status_code == 200
    assert Item.objects.get(sku="A").quantity == 7


def test_R2_locked_shop_user_cannot_cancel(shop_client, shop_user, make_item):
    Admin.objects.create(id=1, edit_lock=True)
    item = make_item(sku="A")
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
    r = post_complete(shop_client, "A", 1, shop_user.username, cancel="true")
    assert r.status_code == 400
    assert TransferItem.objects.count() == 1


def test_R2_set_lock_only_managers(manager_client, shop_client, app_config):
    assert shop_client.post(reverse("set_edit_lock_status"), {"edit_lock_status": True}, format="json").status_code == 403
    assert Admin.is_edit_locked() is False
    r = manager_client.post(reverse("set_edit_lock_status"), {"edit_lock_status": True}, format="json")
    assert r.status_code == 200 and Admin.is_edit_locked() is True


def test_R2_unlocked_without_config_row_allows_transfer(shop_client, make_item):
    make_item(sku="A", quantity=5)  # no Admin row exists
    assert post_transfer(shop_client, "A", 1).status_code == 200


# ---------- R3: state change Draft -> Ordered -> Dispatched / Cancelled ----------
def test_R3_draft_can_be_amended(shop_client, shop_user, make_item, app_config):
    make_item(sku="A", quantity=10)
    post_transfer(shop_client, "A", 2)
    assert post_transfer(shop_client, "A", 5).status_code == 200
    assert TransferItem.objects.get().quantity == 5


def test_R3_submit_marks_ordered(shop_client, shop_user, make_item, app_config):
    make_item(sku="A", quantity=10)
    post_transfer(shop_client, "A", 2)
    assert shop_client.post(reverse(SUBMIT)).status_code == 200
    assert TransferItem.objects.get().ordered is True


def test_R3_ordered_cannot_be_amended(shop_client, shop_user, make_item, app_config):
    make_item(sku="A", quantity=10)
    post_transfer(shop_client, "A", 2)
    shop_client.post(reverse(SUBMIT))
    r = post_transfer(shop_client, "A", 5)
    assert r.status_code == 400
    assert TransferItem.objects.get().quantity == 2


def test_R3_submit_with_nothing_pending_rejected(shop_client, app_config):
    assert shop_client.post(reverse(SUBMIT)).status_code == 400


def test_R3_submit_twice_second_rejected(shop_client, make_item, app_config):
    make_item(sku="A", quantity=10)
    post_transfer(shop_client, "A", 2)
    assert shop_client.post(reverse(SUBMIT)).status_code == 200
    assert shop_client.post(reverse(SUBMIT)).status_code == 400
    assert TransferItem.objects.count() == 1


def test_R3_dispatch_moves_stock_and_clears_pending(manager_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    assert post_complete(manager_client, "A", 4, shop_user.username).status_code == 200
    assert Item.objects.get(sku="A").quantity == 6
    assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 4
    assert TransferItem.objects.count() == 0


def test_R3_dispatch_accumulates_existing_shop_stock(manager_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    ShopItem.objects.create(shop_user=shop_user, item=item, quantity=2)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=3, ordered=True)
    post_complete(manager_client, "A", 3, shop_user.username)
    assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 5


def test_R3_dispatch_over_stock_rejected_nothing_changes(manager_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    r = post_complete(manager_client, "A", 11, shop_user.username)
    assert r.status_code == 400
    assert Item.objects.get(sku="A").quantity == 10
    assert ShopItem.objects.count() == 0
    assert TransferItem.objects.count() == 1


def test_R3_dispatch_twice_second_rejected_no_duplicate(manager_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=4)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    assert post_complete(manager_client, "A", 4, shop_user.username).status_code == 200
    assert post_complete(manager_client, "A", 4, shop_user.username).status_code == 400
    assert Item.objects.get(sku="A").quantity == 0
    assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 4


def test_R3_manager_cancel_removes_pending_stock_unchanged(manager_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    assert post_complete(manager_client, "A", None, shop_user.username, cancel="true").status_code == 200
    assert TransferItem.objects.count() == 0
    assert Item.objects.get(sku="A").quantity == 10


def test_R3_cancel_with_nothing_pending_rejected(manager_client, shop_user, make_item, app_config):
    make_item(sku="A")
    assert post_complete(manager_client, "A", None, shop_user.username, cancel="true").status_code == 400


def test_R3_dispatch_invalid_quantities(manager_client, shop_user, make_item, app_config):
    make_item(sku="A", quantity=10)
    for bad in (0, -1, "x", None):
        assert post_complete(manager_client, "A", bad, shop_user.username).status_code == 400
    assert Item.objects.get(sku="A").quantity == 10


def test_R3_complete_unknown_user_and_item(manager_client, shop_user, make_item, app_config):
    make_item(sku="A")
    assert post_complete(manager_client, "A", 1, "ghost").status_code == 400
    assert post_complete(manager_client, "NOPE", 1, shop_user.username).status_code == 404


# ---------- R4: role permissions ----------
def test_R4_shop_user_cannot_dispatch(shop_client, shop_user, make_item, app_config):
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    assert post_complete(shop_client, "A", 4, shop_user.username).status_code == 403
    assert Item.objects.get(sku="A").quantity == 10


def test_R4_shop_user_can_cancel_own(shop_client, shop_user, make_item, app_config):
    item = make_item(sku="A")
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
    assert post_complete(shop_client, "A", None, shop_user.username, cancel="true").status_code == 200
    assert TransferItem.objects.count() == 0


def test_R4_shop_user_cannot_cancel_others(shop_client, other_shop_user, make_item, app_config):
    item = make_item(sku="A")
    TransferItem.objects.create(shop_user=other_shop_user, item=item, quantity=1)
    assert post_complete(shop_client, "A", None, other_shop_user.username, cancel="true").status_code == 403
    assert TransferItem.objects.count() == 1


def test_R4_manager_cannot_request_transfer(manager_client, make_item, app_config):
    make_item(sku="A")
    assert post_transfer(manager_client, "A", 1).status_code == 403


def test_R4_ungrouped_user_denied(plain_client, make_item, app_config):
    make_item(sku="A")
    assert post_transfer(plain_client, "A", 1).status_code == 403


def test_R4_anonymous_denied(api_client, make_item, app_config):
    make_item(sku="A")
    assert post_transfer(api_client, "A", 1).status_code in (401, 403)
    assert api_client.post(reverse(COMPLETE), {}, format="json").status_code in (401, 403)
    assert api_client.post(reverse(SUBMIT)).status_code in (401, 403)


# ---------- Suspected defect: JSON boolean cancel flag ----------
def test_candidate_defect_json_boolean_cancel_is_treated_as_cancel(manager_client, shop_user, make_item, app_config):
    """cancel=true (JSON boolean) should cancel, not dispatch. Expected to FAIL if defect is real."""
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=shop_user, item=item, quantity=4, ordered=True)
    post_complete(manager_client, "A", None, shop_user.username, cancel=True)
    assert Item.objects.get(sku="A").quantity == 10
    assert TransferItem.objects.count() == 0