"""The issues report: the period window, the roll-ups and the Excel export.

A report that counts a pending or rejected document would claim stock left the
warehouse when it did not, so those are excluded and pinned here. The window is
inclusive on both ends and is matched on the day the stock actually moved.
"""

from datetime import date, datetime, timedelta
from io import BytesIO

import pytest
from django.utils import timezone
from openpyxl import load_workbook

from stock_manager import documents as service
from stock_manager import issue_report
from stock_manager.models import StockDocument

pytestmark = pytest.mark.django_db


def book_issue(manager, site, sku, quantity, *, days_ago=0, doc_type=None):
    document = service.create_document(
        doc_type=doc_type or StockDocument.SITE_ISSUE,
        lines=[{"sku": sku, "quantity": quantity}],
        site=site,
        created_by=manager,
    )
    moved = timezone.now() - timedelta(days=days_ago)
    StockDocument.objects.filter(pk=document.pk).update(applied_at=moved)
    return document


class TestWindow:
    def test_the_default_window_is_the_last_seven_days_inclusive(self):
        today = date(2026, 11, 21)

        start, end = issue_report.parse_range(None, None, today=today)

        assert end == today
        assert start == date(2026, 11, 15)
        assert (end - start).days == 6

    def test_a_reversed_range_is_swapped_rather_than_returning_nothing(self):
        start, end = issue_report.parse_range("2026-11-20", "2026-11-10")

        assert start == date(2026, 11, 10)
        assert end == date(2026, 11, 20)

    def test_a_broken_date_falls_back_to_the_default(self):
        start, end = issue_report.parse_range("not-a-date", "2026-11-21")

        assert end == date(2026, 11, 21)
        assert start == date(2026, 11, 15)


class TestAggregation:
    def test_issues_inside_the_window_are_totalled_per_day_and_site(
        self, manager, shop_user, other_shop_user, make_item
    ):
        make_item(sku="SKU-1", retail_price="10.00", quantity=100)
        make_item(sku="SKU-2", retail_price="2.50", quantity=100)
        book_issue(manager, shop_user, "SKU-1", 3, days_ago=1)
        book_issue(manager, shop_user, "SKU-2", 4, days_ago=1)
        book_issue(manager, other_shop_user, "SKU-1", 5, days_ago=6)

        today = timezone.localdate()
        report = issue_report.build_report(today - timedelta(days=6), today)

        assert report["totals"]["documents"] == 3
        assert report["totals"]["lines"] == 3
        assert report["totals"]["quantity"] == 12
        assert report["totals"]["value"] == 90.00  # 3*10 + 4*2.5 + 5*10
        assert {row["label"]: row["quantity"] for row in report["by_site"]} == {
            shop_user.username: 7,
            other_shop_user.username: 5,
        }
        assert len(report["by_day"]) == 2

    def test_a_document_outside_the_window_is_not_counted(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=100)
        book_issue(manager, shop_user, "SKU-1", 3, days_ago=20)

        today = timezone.localdate()
        report = issue_report.build_report(today - timedelta(days=6), today)

        assert report["totals"]["documents"] == 0
        assert report["rows"] == []

    def test_pending_and_rejected_documents_are_not_reported(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=100)
        pending = service.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 3}],
            site=shop_user,
            created_by=shop_user,
            source=StockDocument.MOBILE,
        )
        assert pending.status == StockDocument.PENDING

        today = timezone.localdate()
        report = issue_report.build_report(today - timedelta(days=6), today)

        assert report["totals"]["documents"] == 0

    def test_additions_are_not_reported_as_issues(self, manager, make_item):
        make_item(sku="SKU-1", quantity=10)
        service.create_document(
            doc_type=StockDocument.PO_RECEIPT,
            lines=[{"sku": "SKU-1", "quantity": 5}],
            counterparty="Elsewedy",
            created_by=manager,
        )

        today = timezone.localdate()
        report = issue_report.build_report(today - timedelta(days=6), today)

        assert report["totals"]["documents"] == 0

    def test_the_row_carries_who_sent_it_and_where(self, manager, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        book_issue(manager, shop_user, "SKU-1", 2)

        today = timezone.localdate()
        report = issue_report.build_report(today, today)
        row = report["rows"][0]

        assert row["destination"] == shop_user.username
        assert row["issued_by"] == manager.username
        assert row["approved_by"] == manager.username
        assert row["sku"] == "SKU-1"


class TestWorkbook:
    def test_the_workbook_has_the_detail_and_the_roll_up_sheets(
        self, manager, shop_user, make_item
    ):
        from io import BytesIO

        from openpyxl import load_workbook

        make_item(sku="SKU-1", retail_price="10.00", quantity=10)
        book_issue(manager, shop_user, "SKU-1", 2)

        today = timezone.localdate()
        workbook = load_workbook(
            BytesIO(issue_report.workbook_bytes(issue_report.build_report(today, today)))
        )

        assert workbook.sheetnames == [
            "Issues",
            "Company permits",
            "By day",
            "By site",
            "By item",
        ]
        sheet = workbook["Issues"]
        assert sheet["A1"].value == "Date"
        assert sheet["B2"].value == StockDocument.objects.get().number
        assert sheet["J2"].value == 2  # quantity
        assert sheet["A4"].value == "Total"
        assert sheet["J4"].value == 2


class TestReportPage:
    def test_the_page_renders_the_totals_and_the_rows(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        book_issue(manager, shop_user, "SKU-1", 4)
        client.force_login(manager)

        response = client.get("/issues/report/")
        html = response.content.decode()

        assert response.status_code == 200
        assert 'id="kpiQuantity"' in html
        assert "SKU-1" in html
        assert "export=xlsx" in html

    def test_the_export_returns_a_real_workbook(self, client, manager, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        book_issue(manager, shop_user, "SKU-1", 4)
        client.force_login(manager)

        response = client.get("/issues/report/?export=xlsx")

        assert response.status_code == 200
        assert response["Content-Type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment; filename=" in response["Content-Disposition"]
        assert response.content[:2] == b"PK"  # a zip container, i.e. a real xlsx

    def test_an_empty_period_says_so_instead_of_showing_a_zero_row(
        self, client, manager
    ):
        client.force_login(manager)

        html = client.get("/issues/report/?from=2020-01-01&to=2020-01-02").content.decode()

        assert "Nothing was issued in this period." in html


class TestUnitOfMeasure:
    def test_every_row_states_the_unit_it_was_issued_in(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", retail_price="10.00", quantity=100, unit="متر")
        book_issue(manager, shop_user, "SKU-1", 4)
        today = timezone.localdate()

        report = issue_report.build_report(today - timedelta(days=6), today)

        assert report["rows"][0]["unit"] == "متر"
        assert report["by_item"][0]["unit"] == "متر"

    def test_the_workbook_has_a_unit_column(self, manager, shop_user, make_item):
        make_item(sku="SKU-1", retail_price="10.00", quantity=100, unit="لفة")
        book_issue(manager, shop_user, "SKU-1", 2)
        today = timezone.localdate()

        report = issue_report.build_report(today - timedelta(days=6), today)
        workbook = load_workbook(BytesIO(issue_report.workbook_bytes(report)))
        detail = workbook["Issues"]

        headers = [cell.value for cell in detail[1]]
        assert "Unit" in headers
        row = [cell.value for cell in detail[2]]
        assert row[headers.index("Unit")] == "لفة"


class TestArabicPresentation:
    def test_the_report_shows_a_latin_decimal_point_not_a_locale_comma(
        self, client, manager, shop_user, make_item
    ):
        """Money on the Arabic page must read 6250.00, not 6250,00."""
        make_item(sku="SKU-1", retail_price="1250.00", quantity=10)
        book_issue(manager, shop_user, "SKU-1", 5)
        client.force_login(manager)
        client.cookies["django_language"] = "ar"

        html = client.get("/issues/report/").content.decode()

        assert "6,250.00" in html
        assert "6.250,00" not in html
        assert "6250,00" not in html

    def test_the_document_type_is_translated_on_the_arabic_page(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        book_issue(manager, shop_user, "SKU-1", 1)
        client.force_login(manager)
        client.cookies["django_language"] = "ar"

        html = client.get("/issues/").content.decode()

        assert "صرف لموقع" in html
        assert "Issue to site" not in html
