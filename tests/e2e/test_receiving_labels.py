"""End-to-end: book a PO delivery, print labels, switch to Arabic.

Both jobs have one screen each: the addition form on /receipts/ and the label
picker on /labels/. The dashboard only points at them.
"""

import pytest

from stock_manager.models import Item

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


class TestReceivingFlow:
    def test_a_delivery_is_booked_and_listed(
        self, page, live_server, login, manager, app_config
    ):
        login("manager")
        page.goto(f"{live_server.url}/receipts/")

        page.select_option("#docType", "po_receipt")
        page.fill("#counterparty", "Elsewedy Cables")
        page.fill("#documentForm input[name=reference]", "PO-2026-000777")
        page.fill('#documentLines input[name=sku]', "NSCOM-2001")
        page.fill('#documentLines input[name=description]', "Steel conduit 25mm")
        page.fill('#documentLines input[name=quantity]', "15")
        page.click("#documentForm button[type=submit]")

        # The saved document is announced and listed among the recent ones.
        page.wait_for_selector(".sap-msgstrip--success")
        assert "RCV-" in page.locator(".sap-msgstrip--success").first.inner_text()
        assert "PO-2026-000777" in page.locator("#recentDocuments").inner_text()
        assert Item.objects.get(sku="NSCOM-2001").quantity == 15

    def test_an_incomplete_document_is_refused(
        self, page, live_server, login, manager, app_config
    ):
        # A receipt must name the supplier; without it nothing is booked.
        login("manager")
        page.goto(f"{live_server.url}/receipts/")

        page.select_option("#docType", "po_receipt")
        page.fill('#documentLines input[name=sku]', "NSCOM-2001")
        page.fill('#documentLines input[name=quantity]', "1")
        page.click("#documentForm button[type=submit]")

        page.wait_for_selector(".sap-msgstrip--error")
        assert "supplier" in page.locator(".sap-msgstrip--error").first.inner_text().lower()
        assert not Item.objects.filter(sku="NSCOM-2001").exists()


class TestLabelSheet:
    def test_selecting_items_prints_a_label_per_copy(
        self, page, live_server, login, manager, app_config, make_item
    ):
        make_item(sku="NSCOM-1001", description="Circuit breaker")
        make_item(sku="NSCOM-1002", description="Cable tray")
        login("manager")
        page.goto(f"{live_server.url}/labels/")
        page.wait_for_selector("#labelItemsTable input[type=checkbox]")

        page.check("#checkAll")
        page.fill("#labelPicker input[name=copies]", "2")
        with page.context.expect_page() as new_page:
            page.click("#printLabelsBtn")
        sheet = new_page.value
        sheet.wait_for_load_state()

        assert sheet.locator(".label").count() == 4
        assert sheet.locator(".label svg").count() == 4
        assert "NSCOM-1001" in sheet.content()


class TestArabicInterface:
    def test_switching_to_arabic_turns_the_page_right_to_left(
        self, page, live_server, login, manager, app_config
    ):
        login("manager")

        with page.expect_navigation():
            page.select_option("#languageSelect", "ar")

        assert page.get_attribute("html", "dir") == "rtl"
        assert "أصناف المخزن" in page.content()

        with page.expect_navigation():
            page.select_option("#languageSelect", "en")
        assert page.get_attribute("html", "dir") == "ltr"
