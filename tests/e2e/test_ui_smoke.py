"""
End-to-end smoke tests: drive the real jQuery frontend in a headless
browser against a live Django server, covering the core user flows.
"""

import pytest
from playwright.sync_api import expect

from stock_manager.models import Item, ShopItem, TransferItem

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


class TestTheTwoPages:
    def test_anonymous_visitor_is_sent_to_login(self, page, live_server):
        page.goto(f"{live_server.url}/")
        page.wait_for_url(f"{live_server.url}/accounts/login/?next=/")
        expect(page.locator('input[name="username"]')).to_be_visible()

    def test_manager_gets_the_item_manager_on_the_items_page(
        self, page, live_server, login, manager, app_config, make_item
    ):
        make_item(sku="SKU-1", description="Widget")
        login("manager")
        page.goto(f"{live_server.url}/stock/")

        # The shell states the reader once, on every page.
        expect(page.locator(".sap-user__name")).to_have_text("manager")
        # Managers get the maintenance toggle, add-item panel and editable rows.
        expect(page.locator("#updateModeSwitch")).to_be_visible()
        expect(page.locator("#addItemSection")).to_be_visible()
        expect(
            page.locator('#itemTable1 input[data-sku="SKU-1"][data-field="description"]')
        ).to_have_value("Widget")
        # A manager does not request stock from itself.
        expect(page.locator("#submitTransferRequest")).to_have_count(0)

    def test_shop_user_gets_read_only_rows_and_a_transfer_field(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        item = make_item(sku="SKU-1", description="Widget")
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=2)
        login("shop1")
        page.goto(f"{live_server.url}/stock/")

        expect(page.locator(".sap-user__name")).to_have_text("shop1")
        # Shop users get read-only warehouse rows with a transfer field...
        expect(page.locator("#updateModeSwitch")).to_be_hidden()
        expect(page.locator("#addItemSection")).to_be_hidden()
        expect(page.locator('#itemTable1 input.xferQntField[data-sku="SKU-1"]')).to_be_visible()
        # ...and the site stock is stated by the server on the same page.
        expect(page.locator("#siteStockTable")).to_contain_text("Widget")
        expect(page.locator("#siteStockTable")).to_contain_text("2")

    def test_the_dashboard_is_an_overview_not_a_second_copy(
        self, page, live_server, login, manager, app_config, make_item
    ):
        make_item(sku="SKU-1", description="Widget")
        login("manager")

        # The figures and the request queue are here; the tables are not.
        expect(page.locator("#kpiWarehouse")).to_have_text("1")
        expect(page.locator("#itemTable3")).to_have_count(1)
        expect(page.locator("#itemTable1")).to_have_count(0)
        expect(page.locator("#addItemSection")).to_have_count(0)
        expect(page.locator(".sap-quicklink")).not_to_have_count(0)


class TestSearch:
    def test_warehouse_search_filters_rows(
        self, page, live_server, login, manager, app_config, make_item
    ):
        make_item(sku="ABC", description="Bird feeder")
        make_item(sku="XYZ", description="Dog lead")
        login("manager")
        page.goto(f"{live_server.url}/stock/")
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

        # Entering a quantity on the items page (the field fires on blur)
        # creates a pending transfer, which the dashboard then queues.
        page.goto(f"{live_server.url}/stock/")
        qty_field = page.locator('#itemTable1 input.xferQntField[data-sku="SKU-1"]')
        qty_field.fill("3")
        qty_field.blur()

        page.goto(f"{live_server.url}/")
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

        # The pending line disappears and the warehouse quantity is reduced;
        # the item itself lives on its own page.
        expect(pending_row).to_have_count(0)
        page.goto(f"{live_server.url}/stock/")
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
        page.goto(f"{live_server.url}/stock/")
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
        page.goto(f"{live_server.url}/stock/")

        expect(page.locator(".maintenanceMode")).to_be_visible()
        expect(
            page.locator('#itemTable1 input.xferQntField[data-sku="SKU-1"]')
        ).to_be_disabled()

class TestMobileDrawer:
    def test_the_menu_button_opens_the_sidebar(
        self, page, live_server, login, manager, app_config
    ):
        page.set_viewport_size({"width": 420, "height": 820})
        login("manager")

        page.click("#navToggle")
        page.wait_for_selector("#sideNav.is-open")
        # The panel slides in, so wait for the outcome, not for the class.
        page.wait_for_function(
            "() => document.getElementById('sideNav').getBoundingClientRect().left >= 0"
        )

        page.click("#sideNav a[data-nav='items']")
        page.wait_for_url("**/stock/")

    def test_escape_closes_the_drawer(self, page, live_server, login, manager, app_config):
        page.set_viewport_size({"width": 420, "height": 820})
        login("manager")

        page.click("#navToggle")
        page.wait_for_selector("#sideNav.is-open")
        page.keyboard.press("Escape")
        page.wait_for_selector("#sideNav:not(.is-open)")
