"""
End-to-end smoke tests: drive the real jQuery frontend in a headless
browser against a live Django server, covering the core user flows.
"""

import pytest
from playwright.sync_api import expect

from stock_manager.models import Item, ShopItem, TransferItem

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestDashboardTailoring:
    def test_anonymous_visitor_is_sent_to_login(self, page, live_server):
        page.goto(f"{live_server.url}/")
        page.wait_for_url(f"{live_server.url}/accounts/login/?next=/")
        expect(page.locator('input[name="username"]')).to_be_visible()

    def test_manager_dashboard(self, page, live_server, login, manager, app_config, make_item):
        make_item(sku="SKU-1", description="Widget")
        login("manager")

        expect(page.locator("#userStatus")).to_contain_text("Hello manager")
        # Managers get the maintenance toggle, add-item panel and editable rows.
        expect(page.locator("#updateModeSwitch")).to_be_visible()
        expect(page.locator("#addItemSection")).to_be_visible()
        expect(
            page.locator('#itemTable1 input[data-sku="SKU-1"][data-field="description"]')
        ).to_have_value("Widget")
        # The shop stock panel and transfer-request button are hidden.
        expect(page.locator(".shop-stock")).to_be_hidden()
        expect(page.locator("#submitTransferRequest")).to_be_hidden()

    def test_shop_user_dashboard(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        item = make_item(sku="SKU-1", description="Widget")
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=2)
        login("shop1")

        expect(page.locator("#userStatus")).to_contain_text("Hello shop1")
        # Shop users get read-only warehouse rows with a transfer field...
        expect(page.locator("#updateModeSwitch")).to_be_hidden()
        expect(page.locator("#addItemSection")).to_be_hidden()
        expect(page.locator('#itemTable1 input.xferQntField[data-sku="SKU-1"]')).to_be_visible()
        expect(page.locator("#submitTransferRequest")).to_be_visible()
        # ...and their own shop stock panel.
        expect(page.locator(".shop-stock")).to_be_visible()
        expect(page.locator("#quantity2-SKU-1")).to_have_value("2")


class TestSearch:
    def test_warehouse_search_filters_rows(
        self, page, live_server, login, manager, app_config, make_item
    ):
        make_item(sku="ABC", description="Bird feeder")
        make_item(sku="XYZ", description="Dog lead")
        login("manager")
        expect(page.locator("#itemTable1 tr")).to_have_count(2)

        # The search box listens for keyup, so type rather than fill.
        page.locator("#searchBox1").press_sequentially("bird")

        expect(page.locator("#itemTable1 tr")).to_have_count(1)
        expect(page.locator("#itemTable1")).to_contain_text("ABC")
        expect(page.locator("#itemTable1")).not_to_contain_text("XYZ")


class TestTransferFlow:
    def test_shop_user_requests_and_submits_transfer(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        item = make_item(sku="SKU-1", quantity=10)
        login("shop1")

        # Entering a quantity (field fires on blur) creates a pending transfer.
        qty_field = page.locator('#itemTable1 input.xferQntField[data-sku="SKU-1"]')
        qty_field.fill("3")
        qty_field.blur()

        pending_row = page.locator('#itemTable3 tr[data-sku="SKU-1"]')
        expect(pending_row).to_have_attribute("data-quantity", "3")
        expect(pending_row).to_have_attribute("data-ordered", "false")

        # Sending the request locks the line in: highlighted and not cancellable.
        page.click("#submitTransferRequest")

        expect(pending_row).to_have_attribute("data-ordered", "true")
        expect(pending_row).to_have_class("highlight-ordered")
        expect(page.locator("#deleteButton-SKU-1")).to_be_disabled()

        transfer = TransferItem.objects.get(shop_user=shop_user, item=item)
        assert transfer.quantity == 3
        assert transfer.ordered is True
        item.refresh_from_db()
        assert item.quantity == 10  # unchanged until the manager dispatches

    def test_shop_user_cancels_pending_transfer(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        item = make_item(sku="SKU-1", quantity=10)
        TransferItem.objects.create(shop_user=shop_user, item=item, quantity=3)
        login("shop1")

        pending_row = page.locator('#itemTable3 tr[data-sku="SKU-1"]')
        expect(pending_row).to_be_visible()
        page.click("#deleteButton-SKU-1")

        expect(pending_row).to_have_count(0)
        assert not TransferItem.objects.filter(shop_user=shop_user, item=item).exists()

    def test_manager_dispatches_transfer(
        self, page, live_server, login, manager, shop_user, app_config, make_item
    ):
        item = make_item(sku="SKU-1", quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        login("manager")

        pending_row = page.locator('#itemTable3 tr[data-sku="SKU-1"]')
        expect(pending_row).to_contain_text("shop1")
        page.click("#dispatchButton-SKU-1")

        # The pending line disappears and the warehouse quantity is reduced.
        expect(pending_row).to_have_count(0)
        expect(
            page.locator('#itemTable1 input[data-sku="SKU-1"][data-field="quantity"]')
        ).to_have_value("6")

        item.refresh_from_db()
        assert item.quantity == 6
        assert ShopItem.objects.get(shop_user=shop_user, item=item).quantity == 4
        assert not TransferItem.objects.filter(shop_user=shop_user, item=item).exists()


class TestMaintenanceMode:
    def test_manager_enables_maintenance_mode(
        self, page, live_server, login, manager, app_config, make_item
    ):
        from stock_manager.models import Admin

        make_item(sku="SKU-1")
        login("manager")
        expect(page.locator(".maintenanceMode")).to_be_hidden()

        page.click("#updateModeSwitch")

        # The banner appears and the lock is persisted. (Manager fields stay
        # editable by design: maintenance mode pauses shop transfers while
        # the manager maintains stock.)
        expect(page.locator(".maintenanceMode")).to_be_visible()
        expect(page.locator("#updateModeToggle")).to_be_checked()
        assert Admin.is_edit_locked() is True

    def test_shop_user_transfers_disabled_during_maintenance(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        app_config.edit_lock = True
        app_config.save()
        make_item(sku="SKU-1", quantity=10)
        login("shop1")

        expect(page.locator(".maintenanceMode")).to_be_visible()
        expect(
            page.locator('#itemTable1 input.xferQntField[data-sku="SKU-1"]')
        ).to_be_disabled()
