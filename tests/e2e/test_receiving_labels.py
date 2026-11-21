"""End-to-end: receive a PO delivery, print labels, switch to Arabic."""

import pytest

from stock_manager.models import Item

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


class TestReceivingFlow:
    def test_a_delivery_is_booked_and_listed(self, page, live_server, login, manager, app_config):
        login("manager")

        page.fill("#poNumber", "PO-2026-000777")
        page.fill("#poSupplier", "Elsewedy Cables")
        page.fill('#receiptLines .sap-line [data-line="sku"]', "NSCOM-2001")
        page.fill('#receiptLines .sap-line [data-line="description"]', "Steel conduit 25mm")
        page.fill('#receiptLines .sap-line [data-line="quantity"]', "15")
        page.click("#receiveBtn")

        page.wait_for_selector("#receiptsBody tr")
        row = page.locator("#receiptsBody tr").first
        assert "PO-2026-000777" in row.inner_text()
        assert "Elsewedy Cables" in row.inner_text()
        assert Item.objects.get(sku="NSCOM-2001").quantity == 15

    def test_a_delivery_without_a_po_number_is_refused(self, page, live_server, login, manager, app_config):
        login("manager")

        page.fill('#receiptLines .sap-line [data-line="sku"]', "NSCOM-2001")
        page.click("#receiveBtn")

        page.wait_for_selector(".sap-toast")
        assert "purchase order" in page.locator(".sap-toast").first.inner_text().lower()
        assert not Item.objects.filter(sku="NSCOM-2001").exists()


class TestLabelSheet:
    def test_selecting_items_prints_a_label_per_copy(
        self, page, live_server, login, manager, app_config, make_item
    ):
        make_item(sku="NSCOM-1001", description="Circuit breaker")
        make_item(sku="NSCOM-1002", description="Cable tray")
        login("manager")
        page.wait_for_selector("#labelList input")

        page.click("#selectAllLabels")
        page.fill("#labelCopies", "2")
        with page.context.expect_page() as new_page:
            page.click("#printLabelsBtn")
        sheet = new_page.value
        sheet.wait_for_load_state()

        assert sheet.locator(".label").count() == 4
        assert sheet.locator(".label svg").count() == 4
        assert "NSCOM-1001" in sheet.content()


class TestArabicInterface:
    def test_switching_to_arabic_turns_the_page_right_to_left(self, page, live_server, login, manager, app_config):
        login("manager")

        with page.expect_navigation():
            page.select_option("#languageSelect", "ar")

        assert page.get_attribute("html", "dir") == "rtl"
        assert "مخزون المخزن" in page.content()

        with page.expect_navigation():
            page.select_option("#languageSelect", "en")
        assert page.get_attribute("html", "dir") == "ltr"
