"""End-to-end: a missing voucher is completed from the page and leaves it.

The operator's rule is a loop, so the test drives the whole loop in a real
browser: the line is listed, the voucher is typed on the row, and the row is
gone afterwards — not merely marked.
"""

import pytest

from stock_manager.models import GoodsReceipt, GoodsReceiptLine

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


def delivery(po_number, skus, supplier="Elsewedy Electric"):
    receipt = GoodsReceipt.objects.create(po_number=po_number, supplier=supplier)
    for sku in skus:
        GoodsReceiptLine.objects.create(
            receipt=receipt, sku=sku, description=f"{sku} article", quantity=2
        )
    return receipt


class TestMissingPaperwork:
    def test_the_page_is_reachable_from_the_sidebar(
        self, page, live_server, login, manager, app_config
    ):
        login("manager")
        page.goto(f"{live_server.url}/")

        page.click('a[data-nav="reconciliation"]')

        page.wait_for_url(f"{live_server.url}/reconciliation/")
        assert page.locator("#missingRows").is_visible()

    def test_a_three_line_delivery_is_completed_from_the_page(
        self, page, live_server, login, manager, app_config
    ):
        delivery("PO-E2E-9", ("E2E-A", "E2E-B", "E2E-C"))
        login("manager")
        page.goto(f"{live_server.url}/reconciliation/")

        rows = page.locator("#missingRows tbody tr[data-sku]")
        assert rows.count() == 3, "every line of the delivery is its own row"

        row = page.locator('#missingRows tbody tr[data-sku="E2E-B"]')
        row.locator('input[name="external_ref"]').fill("V-E2E-9")
        row.locator('button[type="submit"]').click()

        page.wait_for_selector(".sap-msgstrip__title")
        page.wait_for_selector(
            '#missingRows tbody tr[data-sku="E2E-B"]', state="detached"
        )
        assert page.locator("#missingRows tbody tr[data-sku]").count() == 0

    def test_an_empty_voucher_is_refused_by_the_browser(
        self, page, live_server, login, manager, app_config
    ):
        delivery("PO-E2E-10", ("E2E-D",))
        login("manager")
        page.goto(f"{live_server.url}/reconciliation/")

        page.click('#missingRows tbody tr[data-sku="E2E-D"] button[type="submit"]')

        # The field is required, so the browser never posts an empty voucher.
        page.wait_for_timeout(300)
        assert page.url.endswith("/reconciliation/")
        assert GoodsReceipt.objects.get(po_number="PO-E2E-10").external_ref is None
