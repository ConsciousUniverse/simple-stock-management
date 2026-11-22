"""End-to-end: one issue, several company permits, each with its own items.

The operator's case is a single issue paid against three permits
(050340604, 0503537228, 05245322), and the question is which items each permit
covers. The test drives the real form in a browser — including the plain save
that used to wipe every amount because a localised number is rejected by an
``<input type="number">``.
"""

import pytest

from stock_manager import documents as service
from stock_manager import permits
from stock_manager.models import Item, StockDocument

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def issue(manager, site, skus):
    for sku in skus:
        Item.objects.get_or_create(
            sku=sku,
            defaults={"description": f"{sku} article", "retail_price": "10.00", "quantity": 100},
        )
    return service.create_document(
        doc_type=StockDocument.SITE_ISSUE,
        lines=[{"sku": sku, "quantity": 1} for sku in skus],
        site=site,
        created_by=manager,
    )


class TestCompanyPermits:
    def test_two_permits_are_recorded_with_their_items_from_the_page(
        self, page, live_server, login, manager, shop_user, app_config
    ):
        document = issue(manager, shop_user, ("E2E-P1", "E2E-P2"))
        login("manager")

        page.goto(f"{live_server.url}/issues/report/")
        page.click(f'a[href^="/issues/{document.pk}/permits/"]')
        # The link carries the report window as ``?next=``, so wait for the form
        # rather than for an exact URL.
        page.wait_for_selector("#permitRows")

        page.fill("#permitNo0", "050340604")
        page.fill("#permitAmount0", "20.00")
        page.locator('input[name="items_0"][value]').first.check()
        page.fill("#permitNo1", "0503537228")
        page.fill("#permitAmount1", "30.00")
        page.locator('input[name="items_1"]').nth(1).check()
        page.click("#permitForm button[type=submit]")

        page.wait_for_selector(".sap-msgstrip__title")
        assert page.locator("#kpiUncoveredLines").inner_text().strip() == "0"
        assert list(document.permits.values_list("permit_no", flat=True)) == [
            "050340604",
            "0503537228",
        ]

    def test_saving_the_page_without_editing_keeps_the_amounts(
        self, page, live_server, login, manager, shop_user, app_config
    ):
        document = issue(manager, shop_user, ("E2E-P3",))
        permits.save_permits(
            document,
            [{"permit_no": "050340604", "amount": "1250.50", "note": ""}],
            {},
        )
        login("manager")
        # The Arabic interface is where Django localises 1250.50 to "1250,50",
        # which a number input rejects — so the bug only shows in Arabic.
        page.context.add_cookies(
            [{"name": "django_language", "value": "ar", "url": live_server.url}]
        )

        page.goto(f"{live_server.url}/issues/{document.pk}/permits/")
        assert page.input_value("#permitAmount0") == "1250.50"
        page.click("#permitForm button[type=submit]")
        page.wait_for_selector(".sap-msgstrip__title")

        assert str(document.permits.get().amount) == "1250.50"

    def test_a_shop_user_sees_the_permits_without_being_able_to_change_them(
        self, page, live_server, login, manager, shop_user, app_config
    ):
        document = issue(manager, shop_user, ("E2E-P4",))
        permits.save_permits(
            document, [{"permit_no": "050340604", "amount": "10.00", "note": ""}], {}
        )
        login("shop1")

        page.goto(f"{live_server.url}/issues/{document.pk}/permits/")

        assert page.locator("#permitRows").is_visible()
        assert page.locator("#permitForm button[type=submit]").count() == 0
        assert page.locator('input[name="permit_no_0"]').count() == 0
