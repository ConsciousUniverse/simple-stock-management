"""
Member 1: MCC (all 8 combinations) for the permission decision in complete_transfer.

Conditions:  M = requester is a manager
             C = cancel flag is the string "true"
             O = target shop user is the requester
Decision:    permission granted  =  M or (C and O)
"""
import pytest
from django.urls import reverse
from stock_manager.models import TransferItem

#       row, M,     C,     O,     allowed
ROWS = [
    (1, False, False, False, False),
    (2, False, False, True,  False),
    (3, False, True,  False, False),
    (4, False, True,  True,  True),
    (5, True,  False, False, True),
    (6, True,  False, True,  True),
    (7, True,  True,  False, True),
    (8, True,  True,  True,  True),
]


@pytest.mark.parametrize("row,M,C,O,allowed", ROWS, ids=[f"MCC-row{r[0]}" for r in ROWS])
def test_permission_mcc(row, M, C, O, allowed, manager, shop_user, other_shop_user,
                        make_item, app_config, manager_client, shop_client):
    actor = manager if M else shop_user
    client = manager_client if M else shop_client
    other = shop_user if M else other_shop_user
    target = actor if O else other
    item = make_item(sku="A", quantity=10)
    TransferItem.objects.create(shop_user=target, item=item, quantity=2, ordered=True)

    body = {"sku": "A", "quantity": 2, "shop_user_id": target.username}
    if C:
        body["cancel"] = "true"
    r = client.post(reverse("complete_transfer"), body, format="json")

    if allowed:
        assert r.status_code == 200
    else:
        assert r.status_code == 403
        assert TransferItem.objects.filter(shop_user=target, item=item).exists()


# MC/DC pairs (only one condition changes, outcome changes):
#   M : rows 3 -> 7
#   C : rows 2 -> 4
#   O : rows 3 -> 4
# Minimal MC/DC set = rows 2, 3, 4, 7  (n + 1 = 4 tests)