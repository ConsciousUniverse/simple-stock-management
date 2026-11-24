"""The missing-paperwork page: one row per line, and the action that closes it.

The operator's rule is that a line stays on this page until it is completed
from it. These tests pin both halves of that sentence: what gets listed (per
LINE, never per document) and what makes it disappear.
"""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from stock_manager import documents, reconciliation
from stock_manager.models import GoodsReceipt, GoodsReceiptLine, StockDocument

pytestmark = pytest.mark.django_db


def receive(po_number="PO-2026-1", skus=("SKU-1",), supplier="ACME"):
    """A purchase-order delivery as the receipts screen books it."""
    receipt = GoodsReceipt.objects.create(po_number=po_number, supplier=supplier)
    for sku in skus:
        GoodsReceiptLine.objects.create(
            receipt=receipt, sku=sku, description=f"{sku} description", quantity=5
        )
    return receipt


def book_addition(po_number, sku, permit="V-ADD-1", quantity=5):
    """The same goods documented properly, as the additions screen does."""
    return documents.create_document(
        doc_type=StockDocument.PO_RECEIPT,
        lines=[{"sku": sku, "quantity": quantity}],
        counterparty="ACME",
        reference=po_number,
        external_ref=permit,
    )


def skus_of(rows):
    return sorted(row.sku for row in rows)


class TestWhatIsListed:
    def test_one_uncovered_line_of_three_shows_one_row(self):
        """A multi-line order with one undocumented line shows that line only."""
        receive(po_number="PO-2026-9", skus=("SKU-A", "SKU-B", "SKU-C"))
        book_addition("PO-2026-9", "SKU-A", permit="V-ADD-9")

        rows = reconciliation.build_rows()

        assert skus_of(rows) == ["SKU-B", "SKU-C"]
        assert {row.reason for row in rows} == {reconciliation.RECEIPT_WITHOUT_PERMIT}

    def test_a_multi_line_document_shows_one_row_per_line(self, make_item, shop_user):
        """A document is not one row: each of its lines is its own gap."""
        for sku in ("SKU-L1", "SKU-L2", "SKU-L3"):
            make_item(sku=sku, quantity=10)
        documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[
                {"sku": "SKU-L1", "quantity": 1},
                {"sku": "SKU-L2", "quantity": 1},
                {"sku": "SKU-L3", "quantity": 1},
            ],
            site=shop_user,
        )

        rows = reconciliation.build_rows()

        assert skus_of(rows) == ["SKU-L1", "SKU-L2", "SKU-L3"]

    def test_a_fully_documented_delivery_is_not_listed(self):
        receive(po_number="PO-2026-2", skus=("SKU-1",))
        book_addition("PO-2026-2", "SKU-1", permit="V-ADD-2")

        assert reconciliation.build_rows() == []

    def test_an_approved_document_without_a_voucher_is_listed(
        self, make_item, shop_user
    ):
        make_item(sku="SKU-1", quantity=10)
        documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
        )

        rows = reconciliation.build_rows()

        assert [row.reason for row in rows] == [reconciliation.PERMIT_MISSING]
        assert rows[0].needs_permit is True

    def test_a_pending_issue_is_listed_because_the_report_cannot_show_it(
        self, make_item, shop_user
    ):
        make_item(sku="SKU-1", quantity=10)
        documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            pending=True,
            source=StockDocument.MOBILE,
        )

        rows = reconciliation.build_rows()

        assert [row.reason for row in rows] == [reconciliation.ISSUE_PENDING]
        assert rows[0].pending is True

    def test_a_rejected_document_is_not_listed(self, make_item, shop_user):
        """Nothing moved, so there is nothing to chase."""
        make_item(sku="SKU-1", quantity=10)
        document = documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            pending=True,
        )
        documents.reject_document(document)

        assert reconciliation.build_rows() == []

    def test_a_complete_document_is_not_listed(self, make_item, shop_user):
        make_item(sku="SKU-1", quantity=10)
        documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            external_ref="V-COMPLETE",
        )

        assert reconciliation.build_rows() == []

    def test_a_return_to_the_supplier_is_listed(self, make_item):
        make_item(sku="SKU-1", quantity=10)
        documents.create_document(
            doc_type=StockDocument.SUPPLIER_RETURN,
            lines=[{"sku": "SKU-1", "quantity": 1}],
            counterparty="ACME",
        )

        assert [row.reason for row in reconciliation.build_rows()] == [
            reconciliation.PERMIT_MISSING
        ]

    def test_a_transfer_to_another_project_is_listed(self, make_item):
        make_item(sku="SKU-1", quantity=10)
        documents.create_document(
            doc_type=StockDocument.PROJECT_TRANSFER_OUT,
            lines=[{"sku": "SKU-1", "quantity": 1}],
            counterparty="New Capital",
        )

        assert [row.reason for row in reconciliation.build_rows()] == [
            reconciliation.PERMIT_MISSING
        ]

    def test_the_filters_narrow_the_list(self, make_item, shop_user):
        make_item(sku="SKU-1", quantity=10)
        make_item(sku="SKU-2", quantity=10)
        receive(po_number="PO-FILTER", skus=("SKU-1",))
        documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-2", "quantity": 1}],
            site=shop_user,
        )

        only_receipts = reconciliation.build_rows(
            reason=reconciliation.RECEIPT_WITHOUT_PERMIT
        )
        by_code = reconciliation.build_rows(query="SKU-2")

        assert skus_of(only_receipts) == ["SKU-1"]
        assert skus_of(by_code) == ["SKU-2"]


class TestClosingALine:
    def test_recording_the_voucher_removes_the_delivery(self):
        receipt = receive(po_number="PO-CLOSE-1", skus=("SKU-1",))
        assert len(reconciliation.build_rows()) == 1

        reconciliation.record_receipt_permit(receipt, "V-CLOSE-1")

        assert reconciliation.build_rows() == []

    def test_a_permit_alone_does_not_close_a_pending_issue(
        self, make_item, shop_user
    ):
        """An unapproved issue still never reaches the report — it must stay."""
        make_item(sku="SKU-1", quantity=10)
        document = documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 2}],
            site=shop_user,
            pending=True,
        )

        reconciliation.record_permit(document, "V-PENDING-1")
        # Still pending, so the row stays — the approval is the gap that matters.
        assert [row.reason for row in reconciliation.build_rows()] == [
            reconciliation.ISSUE_PENDING
        ]

        reconciliation.record_permit(document, "V-PENDING-1", approve=True)

        assert reconciliation.build_rows() == []

    def test_a_voucher_is_booked_once(self):
        receipt = receive(po_number="PO-UNIQ-1", skus=("SKU-1",))
        other = receive(po_number="PO-UNIQ-2", skus=("SKU-2",))
        reconciliation.record_receipt_permit(receipt, "V-UNIQ")

        with pytest.raises(documents.DocumentError):
            reconciliation.record_receipt_permit(other, "V-UNIQ")

    def test_a_voucher_cannot_cover_both_a_document_and_a_delivery(
        self, make_item, shop_user
    ):
        make_item(sku="SKU-1", quantity=10)
        receipt = receive(po_number="PO-CROSS-1", skus=("SKU-1",))
        document = documents.create_document(
            doc_type=StockDocument.SITE_ISSUE,
            lines=[{"sku": "SKU-1", "quantity": 1}],
            site=shop_user,
            external_ref="V-CROSS",
        )

        with pytest.raises(documents.DocumentError):
            reconciliation.record_receipt_permit(receipt, "V-CROSS")

        document.refresh_from_db()
        assert document.external_ref == "V-CROSS"

    def test_an_empty_voucher_is_refused(self):
        receipt = receive(po_number="PO-EMPTY-1", skus=("SKU-1",))

        with pytest.raises(documents.DocumentError):
            reconciliation.record_receipt_permit(receipt, "   ")

        receipt.refresh_from_db()
        assert receipt.external_ref is None


class TestThePage:
    def test_the_page_lists_the_line_and_its_reason(self, client, manager):
        receive(po_number="PO-PAGE-1", skus=("SKU-PAGE",))
        client.force_login(manager)

        response = client.get("/reconciliation/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "SKU-PAGE" in body
        assert 'id="missingRows"' in body
        assert (
            str(reconciliation.REASON_LABELS[reconciliation.RECEIPT_WITHOUT_PERMIT])
            in body
        )

    def test_a_manager_completes_a_line_from_the_page(self, client, manager):
        receipt = receive(po_number="PO-PAGE-2", skus=("SKU-PAGE-2",))
        client.force_login(manager)

        response = client.post(
            f"/reconciliation/receipts/{receipt.pk}/permit",
            {"external_ref": "V-FROM-PAGE", "next": "/reconciliation/"},
        )

        assert response.status_code == 302
        receipt.refresh_from_db()
        assert receipt.external_ref == "V-FROM-PAGE"
        assert reconciliation.build_rows() == []

    def test_a_shop_user_cannot_complete_a_line(self, client, shop_user):
        receipt = receive(po_number="PO-PAGE-3", skus=("SKU-PAGE-3",))
        client.force_login(shop_user)

        client.post(
            f"/reconciliation/receipts/{receipt.pk}/permit",
            {"external_ref": "V-NOT-ALLOWED"},
        )

        receipt.refresh_from_db()
        assert receipt.external_ref is None

    def test_the_page_requires_a_login(self, client):
        response = client.get("/reconciliation/")

        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]

    def test_the_export_is_a_workbook_with_one_row_per_line(self, client, manager):
        receive(po_number="PO-EXPORT-1", skus=("SKU-E1", "SKU-E2"))
        client.force_login(manager)

        response = client.get("/reconciliation/export/")

        assert response.status_code == 200
        assert response["Content-Type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        sheet = load_workbook(BytesIO(response.content)).active
        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        assert sorted(row[6] for row in rows) == ["SKU-E1", "SKU-E2"]
