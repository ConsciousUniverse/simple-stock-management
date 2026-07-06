"""
End-to-end XSS regression tests.

The frontend renders server-supplied item data (SKU, description, shop
username) into the DOM. These tests seed hostile values and assert the
payload is rendered inertly — the injected script must never execute.

Each malicious payload sets `window.__xss = true` if it runs; the tests
assert that flag never becomes truthy.
"""

import pytest
from playwright.sync_api import expect

from stock_manager.models import ShopItem, TransferItem

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

# Fires only if the browser executes it as HTML/JS rather than showing text.
IMG_PAYLOAD = '<img src=x onerror="window.__xss=true">'
# Breaks out of a double-quoted attribute value, then injects an image.
ATTR_BREAKOUT_PAYLOAD = '"><img src=x onerror="window.__xss=true">'


def xss_fired(page):
    return page.evaluate("() => window.__xss === true")


class TestStoredXSS:
    def test_description_in_readonly_cell_is_inert(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        # Shop users see the warehouse description rendered straight into a
        # <td>, so an <img onerror> would execute if not escaped.
        make_item(sku="SKU-1", description=IMG_PAYLOAD)
        login("shop1")

        expect(page.locator("#itemTable1")).to_contain_text(IMG_PAYLOAD)
        assert xss_fired(page) is False

    def test_description_in_manager_input_is_inert(
        self, page, live_server, login, manager, app_config, make_item
    ):
        # Managers get the description inside an <input value="...">, so an
        # attribute-breakout payload would execute if not escaped.
        make_item(sku="SKU-1", description=ATTR_BREAKOUT_PAYLOAD)
        login("manager")

        field = page.locator('#itemTable1 input[data-field="description"]')
        expect(field).to_have_value(ATTR_BREAKOUT_PAYLOAD)
        assert xss_fired(page) is False

    def test_shop_stock_description_is_inert(
        self, page, live_server, login, shop_user, app_config, make_item
    ):
        item = make_item(sku="SKU-1", description=IMG_PAYLOAD)
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        login("shop1")

        expect(page.locator("#itemTable2")).to_contain_text(IMG_PAYLOAD)
        assert xss_fired(page) is False


class TestTransferButtonInjection:
    def test_action_buttons_carry_sku_as_data_not_inline_js(
        self, page, live_server, login, manager, shop_user, app_config, make_item
    ):
        # The dispatch/cancel buttons must not interpolate the SKU into an
        # inline onclick handler (a SKU containing a quote could then inject
        # JS that runs on click). They must carry the SKU as a data
        # attribute and dispatch via a delegated handler instead.
        evil_sku = "x');window.__xss=true;//"
        item = make_item(sku=evil_sku, description="Widget")
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=2, ordered=True
        )
        login("manager")

        expect(page.locator("#itemTable3")).to_contain_text("Widget")
        action_buttons = page.locator("#itemTable3 td.actions button")
        expect(action_buttons).not_to_have_count(0)
        for i in range(action_buttons.count()):
            button = action_buttons.nth(i)
            assert button.get_attribute("onclick") is None
            assert button.get_attribute("data-sku") == evil_sku
        assert xss_fired(page) is False

    def test_dispatch_still_works_with_ordinary_sku(
        self, page, live_server, login, manager, shop_user, app_config, make_item
    ):
        # The delegated handler replacing the inline onclick must still
        # dispatch correctly.
        item = make_item(sku="SKU-1", quantity=10)
        TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        login("manager")

        page.click("#dispatchButton-SKU-1")

        expect(page.locator('#itemTable3 tr[data-sku="SKU-1"]')).to_have_count(0)
        item.refresh_from_db()
        assert item.quantity == 6


class TestUsernameXSS:
    def test_own_username_rendered_inertly_in_userstatus(
        self, page, live_server, login, groups, app_config
    ):
        # The greeting in #userStatus is built with .html(), so a username
        # containing markup must be escaped. Usernames are normally validated
        # to exclude such characters, but this guards the sink regardless.
        from django.contrib.auth.models import User

        user = User.objects.create_user(username=IMG_PAYLOAD, password="test-pass-123")
        user.groups.add(groups["shop_users"])

        login(IMG_PAYLOAD)

        expect(page.locator("#userStatus")).to_contain_text("Hello")
        assert xss_fired(page) is False
