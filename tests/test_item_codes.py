"""Our internal code over one or more Oracle item codes.

The operator's case: Oracle carries the same article under several codes, and
the warehouse needs one code and one total for it. The Oracle code stays the key
of every movement — this feature adds a grouping, it never rewrites history.
"""

from io import BytesIO

import pytest
from django.db import IntegrityError
from django.utils import timezone
from openpyxl import load_workbook

from stock_manager import documents as service
from stock_manager import item_codes, issue_report, mobile_api
from stock_manager.models import Item, ItemGroup, StockDocument

pytestmark = pytest.mark.django_db


def share(make_item):
    """Two Oracle codes of one article, under one internal code."""
    first = make_item(sku="ORACLE-A", quantity=5)
    second = make_item(sku="ORACLE-B", quantity=7)
    group = item_codes.merge_codes([first.sku, second.sku])
    first.refresh_from_db()
    second.refresh_from_db()
    return first, second, group


class TestEveryItemHasACode:
    def test_a_new_item_is_given_its_own_internal_code(self, make_item):
        first = make_item(sku="ORACLE-A")
        second = make_item(sku="ORACLE-B")

        assert first.internal_code == "00001"
        assert second.internal_code == "00002"
        assert first.internal_group_id != second.internal_group_id

    def test_a_row_that_lost_its_code_is_given_one_on_the_next_save(self, make_item):
        item = make_item()
        Item.objects.filter(pk=item.pk).update(internal_group=None)
        item.refresh_from_db()

        item.quantity = 3
        item.save()

        assert item.internal_code
        assert ItemGroup.objects.filter(code=item.internal_code).exists()

    def test_the_code_is_generated_never_typed(self, make_item):
        item = make_item()
        with pytest.raises(IntegrityError):
            ItemGroup.objects.create(code=item.internal_code)


class TestGrouping:
    def test_two_oracle_codes_share_one_code_and_keep_their_quantities(
        self, make_item
    ):
        first, second, group = share(make_item)

        assert first.internal_code == second.internal_code == group.code
        assert (first.quantity, second.quantity) == (5, 7)

    def test_the_total_is_the_sum_of_the_member_rows(self, make_item):
        first, second, group = share(make_item)

        assert item_codes.group_totals()[group.code] == 12

        second.quantity = 10
        second.save(update_fields=["quantity"])

        assert item_codes.group_totals()[group.code] == 15

    def test_the_internal_code_a_group_left_behind_is_removed(self, make_item):
        first = make_item(sku="ORACLE-A")
        second = make_item(sku="ORACLE-B")
        old_codes = [first.internal_code, second.internal_code]

        item_codes.merge_codes([first.sku, second.sku])

        assert not ItemGroup.objects.filter(code__in=old_codes).exists()

    def test_moving_one_code_does_not_touch_its_documents(
        self, manager, shop_user, make_item
    ):
        first, second, _ = share(make_item)
        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": first.sku, "quantity": 2}],
            site=shop_user,
            created_by=manager,
        )
        first.refresh_from_db()
        assert first.quantity == 3

        item_codes.move_code(first.sku, second.internal_code)

        first.refresh_from_db()
        assert document.lines.get().sku == first.sku
        assert first.quantity == 3
        assert first.internal_code == second.internal_code

    def test_a_typed_internal_code_is_booked_as_an_oracle_code(
        self, manager, shop_user, make_item
    ):
        first, second, group = share(make_item)

        document = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": group.code, "quantity": 1}],
            site=shop_user,
            created_by=manager,
        )

        # The member holding the most stock answers; the line still names it.
        assert document.lines.get().sku == second.sku
        second.refresh_from_db()
        assert second.quantity == 6


class TestThePage:
    def test_a_manager_sees_the_code_and_its_total(self, client, manager, make_item):
        first, second, group = share(make_item)
        client.force_login(manager)

        response = client.get("/items/groups/")

        assert response.status_code == 200
        assert group.code in response.content.decode()
        assert response.context["group_totals"][group.code] == 12

    def test_a_shop_user_cannot_open_it(self, client, shop_user):
        client.force_login(shop_user)

        response = client.get("/items/groups/")

        assert response.status_code == 302

    def test_the_page_groups_the_ticked_codes_under_a_new_code(
        self, client, manager, make_item
    ):
        make_item(sku="ORACLE-A")
        make_item(sku="ORACLE-B")
        client.force_login(manager)

        response = client.post(
            "/items/groups/",
            {"action": "merge_new", "skus": ["ORACLE-A", "ORACLE-B"]},
            follow=True,
        )

        assert response.status_code == 200
        first, second = Item.objects.order_by("sku")
        assert first.internal_code == second.internal_code
        assert first.internal_code not in {"00001", "00002"}


class TestTheStockTable:
    def test_the_api_carries_the_internal_code_and_the_group_total(
        self, manager_client, make_item
    ):
        first, second, group = share(make_item)

        response = manager_client.get("/api/items/")

        row = next(r for r in response.data["results"] if r["sku"] == first.sku)
        assert row["internal_code"] == group.code
        assert row["group_total"] == 12
        assert row["group_size"] == 2

    def test_a_row_without_a_group_reports_its_own_quantity(
        self, manager_client, make_item
    ):
        item = make_item(sku="ORACLE-X", quantity=4)
        Item.objects.filter(pk=item.pk).update(internal_group=None)

        response = manager_client.get("/api/items/")

        row = next(r for r in response.data["results"] if r["sku"] == "ORACLE-X")
        assert row["internal_code"] == ""
        assert row["group_total"] == 4
        assert row["group_size"] == 1

    def test_searching_our_code_finds_every_oracle_code_of_the_item(
        self, manager_client, make_item
    ):
        first, second, group = share(make_item)

        response = manager_client.get(f"/api/items/?search={group.code}")

        assert {row["sku"] for row in response.data["results"]} == {
            first.sku,
            second.sku,
        }

    def test_a_page_of_groups_never_splits_one_group(
        self, manager_client, make_item
    ):
        first, second, group = share(make_item)
        make_item(sku="ORACLE-C", quantity=1)

        response = manager_client.get("/api/items/?grouped=1&page_size=1")

        assert response.data["count"] == 3
        assert [row["sku"] for row in response.data["results"]] == [
            first.sku,
            second.sku,
        ]
        assert response.data["first_row"] == 1
        assert response.data["last_row"] == 2
        assert response.data["total_pages"] == 2


class TestTheOtherScreens:
    def test_the_label_sheet_prints_the_internal_code(self, client, manager, make_item):
        first, _, group = share(make_item)
        client.force_login(manager)

        response = client.get(f"/labels/?skus={first.sku}")

        assert group.code in response.content.decode()

    def test_the_mobile_payload_carries_the_code_and_the_group_total(self, make_item):
        first, second, group = share(make_item)

        payload = mobile_api._item_payload(first)

        assert payload["internalCode"] == group.code
        assert payload["groupTotal"] == 12
        assert payload["groupSize"] == 2

    def test_the_issue_workbook_has_an_internal_code_column(
        self, manager, shop_user, make_item
    ):
        first, _, group = share(make_item)
        service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": first.sku, "quantity": 1}],
            site=shop_user,
            created_by=manager,
        )
        today = timezone.localdate()

        workbook = load_workbook(
            BytesIO(issue_report.workbook_bytes(issue_report.build_report(today, today)))
        )
        sheet = workbook["Issues"]

        assert sheet["G1"].value == "Internal code"
        assert sheet["G2"].value == group.code
