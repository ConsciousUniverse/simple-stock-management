"""End-to-end: the unit of measure travels with the goods.

A quantity without a unit is not an answer, so the unit has to survive the whole
trip: typed on the form, stored on the line, shown on the warehouse page and
printed in the report — otherwise the warehouse copy and the report disagree.
"""

import pytest

from stock_manager.models import Item

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


class TestUnitOnTheAdditionForm:
    def test_a_new_item_learns_its_unit_from_the_addition(
        self, page, live_server, login, manager, app_config
    ):
        login("manager")
        page.goto(f"{live_server.url}/receipts/")

        page.select_option("#docType", "po_receipt")
        page.fill("#counterparty", "Elsewedy Electric")
        page.fill('input[name="sku"]', "NSCOM-3001")
        page.fill('input[name="description"]', "Fire alarm cable 2x1.5")
        page.fill('input[name="unit"]', "لفة")
        page.fill('input[name="quantity"]', "6")
        page.click('#documentForm button[type="submit"]')

        page.wait_for_selector(".sap-msgstrip__title")
        assert Item.objects.get(sku="NSCOM-3001").unit == "لفة"

        # The stock page states the unit beside the quantity.
        page.goto(f"{live_server.url}/stock/")
        row = page.locator("#itemTable1 tr", has_text="NSCOM-3001")
        assert "لفة" in row.inner_text()


class TestUnitOnTheIssueForm:
    def test_the_issue_keeps_the_unit_it_was_given(
        self, page, live_server, login, manager, shop_user, app_config, make_item
    ):
        make_item(sku="NSCOM-1002", description="Cable tray", quantity=20, unit="متر")
        login("manager")
        page.goto(f"{live_server.url}/issues/")

        page.select_option("#docType", "site_issue")
        page.select_option("#siteSelect", label="shop1")
        page.fill('input[name="sku"]', "NSCOM-1002")
        page.fill('input[name="unit"]', "متر")
        page.fill('input[name="quantity"]', "5")
        page.click('#documentForm button[type="submit"]')

        page.wait_for_selector(".sap-msgstrip__title")
        # The catalogue unit was not rewritten by a line that stated its own.
        assert Item.objects.get(sku="NSCOM-1002").unit == "متر"

        page.goto(f"{live_server.url}/issues/report/")
        # The header is rendered uppercase by CSS, so compare on the lower case.
        header = page.locator("#reportRows thead").inner_text().lower()
        assert "unit" in header
        assert "متر" in page.locator("#reportRows tbody").inner_text()
