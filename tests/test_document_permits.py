"""Company permits: one issue, several permits, each covering its own items.

The operator's rule is pinned here: an issue dated 1/7 may take permits
050340604, 0503537228 and 05245322, and each permit names the items it covers.
A line belongs to one permit, and a line no permit covers is still a gap — so
the missing-paperwork page keeps listing exactly those lines.
"""

from io import BytesIO

import pytest
from django.http import QueryDict
from django.utils import timezone
from openpyxl import load_workbook

from stock_manager import documents as service
from stock_manager import issue_report, permits, reconciliation
from stock_manager.models import DocumentPermit, StockDocument, StockDocumentLine

pytestmark = pytest.mark.django_db


def make_issue(manager, site, lines, *, doc_type=None):
    """A pending-then-approved issue whose stock really moved."""
    return service.create_document(
        doc_type=doc_type or StockDocument.SITE_ISSUE,
        lines=lines,
        site=site,
        created_by=manager,
    )


def permit_form(*rows):
    """A posted form for the permits page: (number, amount, [line ids])."""
    data = QueryDict("", mutable=True)
    for index, (number, amount, line_ids) in enumerate(rows):
        data[f"permit_no_{index}"] = number
        data[f"permit_amount_{index}"] = amount
        data.setlist(f"items_{index}", [str(line_id) for line_id in line_ids])
    return data


class TestSaving:
    def test_one_issue_takes_several_permits_each_covering_its_items(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", retail_price="10.00", quantity=50)
        make_item(sku="SKU-2", retail_price="20.00", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 2}, {"sku": "SKU-2", "quantity": 3}],
        )
        first, second = document.lines.order_by("id")

        permits.save_permits(
            document,
            [
                {"permit_no": "050340604", "amount": "20.00", "note": ""},
                {"permit_no": "0503537228", "amount": "60.00", "note": ""},
                {"permit_no": "05245322", "amount": "0.00", "note": "باقي الصرفية"},
            ],
            {str(first.pk): "050340604", str(second.pk): "0503537228"},
            user=manager,
        )

        numbers = list(document.permits.values_list("permit_no", flat=True))
        assert numbers == ["050340604", "0503537228", "05245322"]

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.permit.permit_no == "050340604"
        assert second.permit.permit_no == "0503537228"

    def test_the_amount_of_each_permit_is_kept(self, manager, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])

        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "1,250.50", "note": ""}], {}
        )

        assert str(document.permits.get().amount) == "1250.50"

    def test_a_permit_removed_from_the_form_is_dropped_and_its_lines_released(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        line = document.lines.get()
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "5", "note": ""}], {str(line.pk): "A-1"}
        )

        permits.save_permits(document, [], {})

        assert not DocumentPermit.objects.exists()
        line.refresh_from_db()
        assert line.permit_id is None

    def test_a_number_listed_twice_on_one_document_is_refused(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])

        with pytest.raises(permits.PermitError):
            permits.save_permits(
                document,
                [
                    {"permit_no": "A-1", "amount": "5", "note": ""},
                    {"permit_no": "A-1", "amount": "6", "note": ""},
                ],
                {},
            )

        assert not DocumentPermit.objects.exists()

    def test_a_number_recorded_on_another_issue_is_refused(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        first = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        second = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        permits.save_permits(first, [{"permit_no": "A-1", "amount": "5", "note": ""}], {})

        with pytest.raises(permits.PermitError):
            permits.save_permits(
                second, [{"permit_no": "A-1", "amount": "5", "note": ""}], {}
            )

        assert DocumentPermit.objects.filter(document=second).count() == 0

    def test_a_line_ticked_under_two_permits_is_refused(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        line = document.lines.get()

        with pytest.raises(permits.PermitError):
            permits.parse_form(
                permit_form(("A-1", "5", [line.pk]), ("A-2", "5", [line.pk])),
                {str(line.pk)},
            )

    def test_a_bad_amount_is_refused(self, manager, shop_user, make_item):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])

        with pytest.raises(permits.PermitError):
            permits.save_permits(
                document, [{"permit_no": "A-1", "amount": "abc", "note": ""}], {}
            )
        with pytest.raises(permits.PermitError):
            permits.save_permits(
                document, [{"permit_no": "A-1", "amount": "-5", "note": ""}], {}
            )

    def test_a_thousands_separator_is_accepted_but_a_decimal_comma_is_not(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])

        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "1,250.50", "note": ""}], {}
        )
        assert str(document.permits.get().amount) == "1250.50"

        # 1250,50 read as a thousands separator would become 125050.00.
        with pytest.raises(permits.PermitError):
            permits.save_permits(
                document, [{"permit_no": "A-1", "amount": "1250,50", "note": ""}], {}
            )

    def test_a_tick_for_another_documents_line_is_ignored(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        other = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        foreign_line = other.lines.get()

        rows, assignments = permits.parse_form(
            permit_form(("A-1", "5", [foreign_line.pk])), set()
        )

        assert rows and assignments == {}

    def test_blank_rows_are_ignored(self):
        rows, assignments = permits.parse_form(
            permit_form(("", "", [])), set()
        )

        assert rows == [] and assignments == {}


class TestCoverage:
    def test_the_permits_total_is_compared_with_the_issue_value(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", retail_price="10.00", quantity=50)
        make_item(sku="SKU-2", retail_price="20.00", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 2}, {"sku": "SKU-2", "quantity": 3}],
        )
        first, second = document.lines.order_by("id")
        permits.save_permits(
            document,
            [
                {"permit_no": "A-1", "amount": "20.00", "note": ""},
                {"permit_no": "A-2", "amount": "40.00", "note": ""},
            ],
            {str(first.pk): "A-1", str(second.pk): "A-2"},
        )

        result = permits.coverage(document)

        assert result["value"] == 80  # 2x10 + 3x20
        assert result["permit_total"] == 60
        assert result["difference"] == -20
        assert result["uncovered_lines"] == 0
        assert result["documented"] is True

    def test_a_document_is_not_documented_while_a_line_has_no_permit(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=10)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        permits.save_permits(document, [{"permit_no": "A-1", "amount": "5", "note": ""}], {})

        result = permits.coverage(document)

        assert result["documented"] is False
        assert result["uncovered_lines"] == 1


class TestReport:
    def test_the_report_groups_the_items_under_each_permit(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", retail_price="10.00", quantity=50)
        make_item(sku="SKU-2", retail_price="20.00", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 2}, {"sku": "SKU-2", "quantity": 3}],
        )
        first, second = document.lines.order_by("id")
        permits.save_permits(
            document,
            [
                {"permit_no": "050340604", "amount": "20.00", "note": ""},
                {"permit_no": "0503537228", "amount": "60.00", "note": ""},
            ],
            {str(first.pk): "050340604", str(second.pk): "0503537228"},
        )

        today = timezone.localdate()
        report = issue_report.build_report(today, today)

        by_number = {permit["permit_no"]: permit for permit in report["permits"]}
        assert set(by_number) == {"050340604", "0503537228"}
        assert [line.sku for line in by_number["050340604"]["lines"]] == ["SKU-1"]
        assert [line.sku for line in by_number["0503537228"]["lines"]] == ["SKU-2"]
        assert by_number["050340604"]["amount_display"] == "20.00"

        assert report["totals"]["permits"] == 2
        assert report["totals"]["permit_value"] == 80
        assert report["totals"]["uncovered_lines"] == 0

    def test_each_row_names_the_permit_that_covers_it(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        make_item(sku="SKU-2", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 1}, {"sku": "SKU-2", "quantity": 1}],
        )
        first, _second = document.lines.order_by("id")
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "5", "note": ""}], {str(first.pk): "A-1"}
        )

        today = timezone.localdate()
        rows = issue_report.build_report(today, today)["rows"]
        by_sku = {row["sku"]: row["permit_no"] for row in rows}

        assert by_sku == {"SKU-1": "A-1", "SKU-2": ""}

    def test_an_issue_with_a_line_without_a_permit_is_listed_as_needing_one(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        make_item(sku="SKU-2", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 1}, {"sku": "SKU-2", "quantity": 1}],
        )
        first, _second = document.lines.order_by("id")
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "5", "note": ""}], {str(first.pk): "A-1"}
        )

        today = timezone.localdate()
        report = issue_report.build_report(today, today)

        assert [item["number"] for item in report["needs_permits"]] == [document.number]
        assert report["needs_permits"][0]["uncovered"] == 1
        assert report["needs_permits"][0]["permit_numbers"] == "A-1"

    def test_the_workbook_has_a_permits_sheet_with_one_row_per_item(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 2}])
        line = document.lines.get()
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "20", "note": ""}], {str(line.pk): "A-1"}
        )

        today = timezone.localdate()
        workbook = load_workbook(
            BytesIO(issue_report.workbook_bytes(issue_report.build_report(today, today)))
        )
        sheet = workbook["Company permits"]

        assert [cell.value for cell in sheet[1]][:4] == [
            "Date",
            "Document",
            "Company permit",
            "Amount",
        ]
        assert sheet["B2"].value == document.number
        assert sheet["C2"].value == "A-1"
        assert sheet["F2"].value == "SKU-1"
        assert sheet["H2"].value == 2


class TestPermitsPage:
    def test_a_manager_records_the_permits_and_the_items_of_each(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        make_item(sku="SKU-2", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 1}, {"sku": "SKU-2", "quantity": 1}],
        )
        first, second = document.lines.order_by("id")
        client.force_login(manager)

        response = client.post(
            f"/issues/{document.pk}/permits/",
            {
                **permit_form(
                    ("050340604", "20.00", [first.pk]),
                    ("0503537228", "60.00", [second.pk]),
                ),
                "next": "/issues/report/",
            },
        )

        assert response.status_code == 302
        assert response["Location"] == "/issues/report/"
        assert list(document.permits.values_list("permit_no", flat=True)) == [
            "050340604",
            "0503537228",
        ]
        first.refresh_from_db()
        assert first.permit.permit_no == "050340604"

    def test_the_page_lists_the_permits_and_the_lines(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        line = document.lines.get()
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "5", "note": ""}], {str(line.pk): "A-1"}
        )
        client.force_login(manager)

        response = client.get(f"/issues/{document.pk}/permits/")
        html = response.content.decode()

        assert response.status_code == 200
        assert 'id="permitRows"' in html
        assert "A-1" in html
        assert 'id="kpiUncoveredLines"' in html

    def test_a_shop_user_cannot_record_permits(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        client.force_login(shop_user)

        response = client.post(
            f"/issues/{document.pk}/permits/",
            permit_form(("A-1", "5", [])),
        )

        assert response.status_code == 302
        assert not DocumentPermit.objects.exists()

    def test_a_rejected_save_shows_what_was_typed_instead_of_dropping_it(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        client.force_login(manager)

        response = client.post(
            f"/issues/{document.pk}/permits/",
            permit_form(("050340604", "20.00", []), ("", "0", [])),
        )
        html = response.content.decode()

        assert response.status_code == 200
        assert "050340604" in html
        assert not DocumentPermit.objects.exists()


class TestThePageCanBeSavedBackUnchanged:
    """Saving the page without editing must not zero the amounts.

    Django localises a Decimal to ``500,00`` in Arabic, and an ``<input
    type="number">`` silently rejects that — the field comes back EMPTY, so a
    plain save wipes every amount. The guard reads the rendered value back.
    """

    def test_the_amount_inputs_carry_plain_numbers_in_arabic(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "1250.50", "note": ""}], {}
        )
        client.force_login(manager)
        client.cookies["django_language"] = "ar"

        html = client.get(f"/issues/{document.pk}/permits/").content.decode()

        assert 'value="1250.50"' in html
        assert 'value="1250,50"' not in html

    def test_saving_the_page_back_keeps_the_amounts(
        self, client, manager, shop_user, make_item
    ):
        import re

        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "1250.50", "note": ""}], {}
        )
        client.force_login(manager)
        client.cookies["django_language"] = "ar"

        html = client.get(f"/issues/{document.pk}/permits/").content.decode()
        rendered = dict(
            re.findall(
                r'name="(permit_amount_\d+)"[^>]*value="([^"]*)"', html, re.S
            )
        )

        client.post(
            f"/issues/{document.pk}/permits/",
            {"permit_no_0": "A-1", "permit_amount_0": rendered["permit_amount_0"]},
        )

        assert str(document.permits.get().amount) == "1250.50"


class TestReportPage:
    def test_the_report_shows_the_permits_and_the_issues_still_missing_one(
        self, client, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        make_item(sku="SKU-2", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 1}, {"sku": "SKU-2", "quantity": 1}],
        )
        first, _second = document.lines.order_by("id")
        permits.save_permits(
            document,
            [{"permit_no": "050340604", "amount": "20.00", "note": ""}],
            {str(first.pk): "050340604"},
        )
        client.force_login(manager)

        response = client.get("/issues/report/")
        html = response.content.decode()

        assert response.status_code == 200
        assert 'id="permitTable"' in html
        assert "050340604" in html
        assert 'id="needsPermits"' in html
        assert f"/issues/{document.pk}/permits/" in html
        assert 'id="kpiUncoveredLines"' in html


class TestMissingPaperworkFollowsThePermits:
    def test_only_the_lines_without_a_permit_stay_on_the_page(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        make_item(sku="SKU-2", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 1}, {"sku": "SKU-2", "quantity": 1}],
        )
        first, _second = document.lines.order_by("id")
        permits.save_permits(
            document, [{"permit_no": "A-1", "amount": "5", "note": ""}], {str(first.pk): "A-1"}
        )

        rows = reconciliation.build_rows()

        assert [(row.number, row.sku) for row in rows] == [(document.number, "SKU-2")]

    def test_a_fully_permitted_issue_leaves_the_page(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        make_item(sku="SKU-2", quantity=50)
        document = make_issue(
            manager,
            shop_user,
            [{"sku": "SKU-1", "quantity": 1}, {"sku": "SKU-2", "quantity": 1}],
        )
        first, second = document.lines.order_by("id")
        permits.save_permits(
            document,
            [
                {"permit_no": "A-1", "amount": "5", "note": ""},
                {"permit_no": "A-2", "amount": "5", "note": ""},
            ],
            {str(first.pk): "A-1", str(second.pk): "A-2"},
        )

        assert reconciliation.build_rows() == []

    def test_a_voucher_on_the_document_still_documents_every_line(
        self, manager, shop_user, make_item
    ):
        make_item(sku="SKU-1", quantity=50)
        document = make_issue(manager, shop_user, [{"sku": "SKU-1", "quantity": 1}])
        StockDocument.objects.filter(pk=document.pk).update(external_ref="V-1")

        assert reconciliation.build_rows() == []
