from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from stock_manager.models import Item, ShopItem
from stock_manager.utils import HAS_SPREADSHEET_CONVERT

from .conftest import (
    SHOP_HEADER,
    WAREHOUSE_HEADER,
    build_xlsx,
    sheet_rows,
    workbook_from_response,
)

pytestmark = pytest.mark.django_db

EXPORT_URL = "/api/export_data/"
IMPORT_URL = "/api/import_data/"


@pytest.fixture
def uploads_enabled(app_config):
    app_config.allow_uploads = True
    app_config.save()
    return app_config


def post_xlsx(client, sheets, defaults=True):
    """
    Post an .xlsx upload. The app expects both default sheets to be present
    (as produced by its own export); with defaults=True any missing sheet is
    added as a header-only sheet.
    """
    if defaults:
        sheets = {
            "Warehouse Stock": [WAREHOUSE_HEADER],
            "Shop Stock": [SHOP_HEADER],
            **sheets,
        }
    return client.post(IMPORT_URL, {"file": build_xlsx(sheets)}, format="multipart")


class TestExport:
    def test_anonymous_denied(self, api_client):
        assert api_client.get(EXPORT_URL).status_code == 403

    def test_user_without_group_denied(self, plain_client):
        assert plain_client.get(EXPORT_URL).status_code == 403

    def test_download_headers(self, manager_client, make_item):
        make_item()
        response = manager_client.get(EXPORT_URL)
        assert response.status_code == 200
        assert response["Content-Type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "SSM_DATA_" in response["Content-Disposition"]

    def test_warehouse_sheet_contains_active_items_only(
        self, manager_client, make_item
    ):
        make_item(sku="LIVE", description="Widget", retail_price="9.99", quantity=5)
        make_item(sku="DEAD", is_active=False)

        workbook = workbook_from_response(manager_client.get(EXPORT_URL))

        assert workbook.sheetnames == ["Warehouse Stock", "Shop Stock"]
        rows = sheet_rows(workbook["Warehouse Stock"])
        # openpyxl reads numeric cells back as floats.
        assert rows == [("LIVE", "Widget", 9.99, 5)]
        header = next(workbook["Warehouse Stock"].iter_rows(max_row=1, values_only=True))
        assert list(header) == WAREHOUSE_HEADER

    def test_manager_sees_all_shop_stock(
        self, manager_client, shop_user, other_shop_user, make_item
    ):
        ShopItem.objects.create(
            shop_user=shop_user, item=make_item(sku="A"), quantity=1
        )
        ShopItem.objects.create(
            shop_user=other_shop_user, item=make_item(sku="B"), quantity=2
        )

        workbook = workbook_from_response(manager_client.get(EXPORT_URL))

        rows = sheet_rows(workbook["Shop Stock"])
        assert {(row[0], row[1]) for row in rows} == {("shop1", "A"), ("shop2", "B")}
        header = next(workbook["Shop Stock"].iter_rows(max_row=1, values_only=True))
        assert list(header) == SHOP_HEADER

    def test_shop_user_sees_only_own_shop_stock(
        self, shop_client, shop_user, other_shop_user, make_item
    ):
        ShopItem.objects.create(
            shop_user=shop_user, item=make_item(sku="A"), quantity=1
        )
        ShopItem.objects.create(
            shop_user=other_shop_user, item=make_item(sku="B"), quantity=2
        )

        workbook = workbook_from_response(shop_client.get(EXPORT_URL))

        rows = sheet_rows(workbook["Shop Stock"])
        assert [(row[0], row[1]) for row in rows] == [("shop1", "A")]


class TestImportPermissions:
    def test_anonymous_denied(self, api_client, uploads_enabled):
        response = api_client.post(IMPORT_URL, {}, format="multipart")
        assert response.status_code == 403

    def test_non_manager_denied(self, shop_client, uploads_enabled):
        response = post_xlsx(shop_client, {"Warehouse Stock": [WAREHOUSE_HEADER]})
        assert response.status_code == 403

    def test_denied_when_uploads_disabled(self, manager_client, app_config):
        response = post_xlsx(manager_client, {"Warehouse Stock": [WAREHOUSE_HEADER]})
        assert response.status_code == 400
        assert "disabled" in response.json()["detail"]

    def test_missing_file_rejected(self, manager_client, uploads_enabled):
        response = manager_client.post(IMPORT_URL, {}, format="multipart")
        assert response.status_code == 400
        assert "Invalid file format" in response.json()["detail"]

    def test_non_xlsx_extension_rejected(self, manager_client, uploads_enabled):
        bogus = SimpleUploadedFile("stock.txt", b"not a spreadsheet")
        response = manager_client.post(
            IMPORT_URL, {"file": bogus}, format="multipart"
        )
        assert response.status_code == 400
        assert "Invalid file format" in response.json()["detail"]


class TestImportWarehouseSheet:
    def test_creates_new_items(self, manager_client, uploads_enabled):
        response = post_xlsx(
            manager_client,
            {
                "Warehouse Stock": [
                    WAREHOUSE_HEADER,
                    ["NEW-1", "Widget", "9.99", 5],
                    ["NEW-2", "Gadget", "1.50", 0],
                ]
            },
        )
        assert response.status_code == 200
        item = Item.objects.get(sku="NEW-1")
        assert item.description == "Widget"
        assert item.retail_price == Decimal("9.99")
        assert item.quantity == 5
        assert item.is_active is True
        assert Item.objects.filter(sku="NEW-2").exists()

    def test_updates_changed_items(self, manager_client, uploads_enabled, make_item):
        make_item(sku="UPD", description="old", retail_price="1.00", quantity=1)
        response = post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, ["UPD", "new", "£2.50", 7]]},
        )
        assert response.status_code == 200
        item = Item.objects.get(sku="UPD")
        assert item.description == "new"
        assert item.retail_price == Decimal("2.50")
        assert item.quantity == 7

    def test_reactivates_inactive_items_in_sheet(
        self, manager_client, uploads_enabled, make_item
    ):
        make_item(sku="GHOST", is_active=False)
        post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, ["GHOST", "Widget", "9.99", 10]]},
        )
        assert Item.objects.get(sku="GHOST").is_active is True

    def test_rows_without_sku_skipped(self, manager_client, uploads_enabled):
        response = post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, [None, "No sku", "1.00", 1]]},
        )
        assert response.status_code == 200
        assert Item.objects.count() == 0

    def test_missing_items_kept_when_deletions_disabled(
        self, manager_client, uploads_enabled, make_item
    ):
        make_item(sku="KEEP")
        post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, ["OTHER", "x", "1.00", 1]]},
        )
        assert Item.objects.get(sku="KEEP").is_active is True

    def test_missing_items_deactivated_when_deletions_enabled(
        self, manager_client, uploads_enabled, make_item
    ):
        uploads_enabled.allow_upload_deletions = True
        uploads_enabled.save()
        make_item(sku="DROP")
        post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, ["OTHER", "x", "1.00", 1]]},
        )
        # 'Deleted' items are soft-deleted, not removed.
        assert Item.objects.get(sku="DROP").is_active is False

    def test_invalid_price_fails_whole_upload(
        self, manager_client, uploads_enabled
    ):
        response = post_xlsx(
            manager_client,
            {
                "Warehouse Stock": [
                    WAREHOUSE_HEADER,
                    ["OK-1", "x", "1.00", 1],
                    ["BAD-1", "x", "not-a-price", 1],
                ]
            },
        )
        assert response.status_code == 400
        assert "Failed to upload" in response.json()["detail"]
        # The transaction is atomic: nothing is partially imported.
        assert Item.objects.count() == 0


class TestImportShopSheet:
    def shop_sheet(self, *rows):
        return {"Shop Stock": [SHOP_HEADER, *rows]}

    def test_creates_shop_items_for_existing_user_and_item(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        make_item(sku="SKU-1")
        response = post_xlsx(
            manager_client,
            self.shop_sheet(["shop1", "SKU-1", "Widget", "9.99", 4]),
        )
        assert response.status_code == 200
        shop_item = ShopItem.objects.get(shop_user=shop_user, item__sku="SKU-1")
        assert shop_item.quantity == 4

    def test_updates_existing_shop_item_quantity(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        item = make_item(sku="SKU-1")
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        post_xlsx(
            manager_client,
            self.shop_sheet(["shop1", "SKU-1", "Widget", "9.99", 9]),
        )
        assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 9

    def test_unknown_shop_user_row_skipped(
        self, manager_client, uploads_enabled, make_item
    ):
        make_item(sku="SKU-1")
        response = post_xlsx(
            manager_client,
            self.shop_sheet(["ghost-user", "SKU-1", "Widget", "9.99", 4]),
        )
        assert response.status_code == 200
        assert ShopItem.objects.count() == 0

    def test_unknown_sku_creates_inactive_item(
        self, manager_client, uploads_enabled, shop_user
    ):
        response = post_xlsx(
            manager_client,
            self.shop_sheet(["shop1", "SHOP-ONLY", "Shop thing", "3.00", 2]),
        )
        assert response.status_code == 200
        item = Item.objects.get(sku="SHOP-ONLY")
        assert item.is_active is False
        assert ShopItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_invalid_price_reported_as_skipped_sku(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        make_item(sku="SKU-1")
        response = post_xlsx(
            manager_client,
            self.shop_sheet(["shop1", "SKU-1", "Widget", "not-a-price", 4]),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["skipped_skus"] == ["SKU-1"]
        assert "skipped" in body["detail"]

    def test_missing_shop_items_deleted_when_deletions_enabled(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        uploads_enabled.allow_upload_deletions = True
        uploads_enabled.save()
        keep = make_item(sku="KEEP")
        drop = make_item(sku="DROP")
        ShopItem.objects.create(shop_user=shop_user, item=keep, quantity=1)
        ShopItem.objects.create(shop_user=shop_user, item=drop, quantity=1)

        post_xlsx(
            manager_client,
            self.shop_sheet(["shop1", "KEEP", "Widget", "9.99", 1]),
        )

        assert ShopItem.objects.filter(item=keep).exists()
        assert not ShopItem.objects.filter(item=drop).exists()

    def test_missing_shop_items_kept_when_deletions_disabled(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        drop = make_item(sku="DROP")
        ShopItem.objects.create(shop_user=shop_user, item=drop, quantity=1)

        post_xlsx(
            manager_client,
            self.shop_sheet(["shop1", "OTHER", "Widget", "9.99", 1]),
        )

        assert ShopItem.objects.filter(item=drop).exists()


class TestImportSingleSheet:
    """
    Uploads containing only one of the two default sheets must process that
    sheet and leave everything governed by the other sheet untouched.
    """

    def test_warehouse_only_upload_succeeds(self, manager_client, uploads_enabled):
        response = post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, ["NEW-1", "Widget", "9.99", 5]]},
            defaults=False,
        )
        assert response.status_code == 200
        assert Item.objects.filter(sku="NEW-1").exists()

    def test_shop_only_upload_succeeds(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        make_item(sku="SKU-1")
        response = post_xlsx(
            manager_client,
            {"Shop Stock": [SHOP_HEADER, ["shop1", "SKU-1", "Widget", "9.99", 4]]},
            defaults=False,
        )
        assert response.status_code == 200
        assert ShopItem.objects.filter(
            shop_user=shop_user, item__sku="SKU-1"
        ).exists()

    def test_shop_only_upload_never_deactivates_warehouse_items(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        # Deletions apply per sheet: without a Warehouse Stock sheet the
        # upload must not touch warehouse items at all.
        uploads_enabled.allow_upload_deletions = True
        uploads_enabled.save()
        make_item(sku="KEEP")
        response = post_xlsx(
            manager_client,
            {"Shop Stock": [SHOP_HEADER, ["shop1", "KEEP", "Widget", "9.99", 1]]},
            defaults=False,
        )
        assert response.status_code == 200
        assert Item.objects.get(sku="KEEP").is_active is True

    def test_warehouse_only_upload_never_deletes_shop_items(
        self, manager_client, uploads_enabled, shop_user, make_item
    ):
        uploads_enabled.allow_upload_deletions = True
        uploads_enabled.save()
        item = make_item(sku="SKU-1")
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        response = post_xlsx(
            manager_client,
            {"Warehouse Stock": [WAREHOUSE_HEADER, ["SKU-1", "Widget", "9.99", 5]]},
            defaults=False,
        )
        assert response.status_code == 200
        assert ShopItem.objects.filter(shop_user=shop_user, item=item).exists()


@pytest.mark.skipif(
    not HAS_SPREADSHEET_CONVERT,
    reason="custom spreadsheet_convert.py not present (user-supplied, gitignored)",
)
class TestImportCustomSchema:
    def test_unrecognised_workbook_rejected(self, manager_client, uploads_enabled):
        response = post_xlsx(
            manager_client,
            {"Some Random Sheet": [["Foo", "Bar"], [1, 2]]},
            defaults=False,
        )
        assert response.status_code == 400
        assert "conversion failed" in response.json()["detail"]

    def test_custom_schema_converted_and_imported(
        self, manager_client, uploads_enabled, groups
    ):
        from django.contrib.auth.models import User

        mengham = User.objects.create_user(username="shop.mengham", password="x")
        mengham.groups.add(groups["shop_users"])

        response = post_xlsx(
            manager_client,
            {
                "Main stock list": [
                    ["SKUCode", "Item", "BL Price", "Barn", "Feed Barn", "Mengham"],
                    ["CUST-1", "Custom widget", 10.5, 3, 2, 5],
                ]
            },
            defaults=False,
        )

        assert response.status_code == 200
        item = Item.objects.get(sku="CUST-1")
        assert item.quantity == 5  # Barn + Feed Barn
        assert item.retail_price == Decimal("10.50")
        shop_item = ShopItem.objects.get(shop_user=mengham, item=item)
        assert shop_item.quantity == 5
