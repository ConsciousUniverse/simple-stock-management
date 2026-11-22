"""The missing-paperwork page: every line that moved without its document.

The operator's rule for this page is a standing one: anything that was added or
issued and did not end up on a document that can be reported or paid **stays
here** until it is completed from this page, then disappears. It is not a
period report — the list has no default window.

Four reasons, one per gap:

``issue_pending``
    An issue is still waiting for approval. The issues report reads APPROVED,
    applied documents only, so a pending issue can never appear in it even
    though the goods may already be on their way.
``addition_pending``
    An addition is still waiting for approval, so the stock was never increased
    — the goods are on the shelf with nothing in the system saying so.
``permit_missing``
    The document moved stock but carries no company voucher number, so it cannot
    be matched to the company's own paper.
``receipt_without_permit``
    Goods were delivered against a purchase order and booked straight onto the
    shelf by the receipts screen — which writes no stock document at all — and
    the delivery has no voucher number. Nothing else records that delivery, so
    it is listed here.

Rows are per LINE, not per document: a ten-line order with one undocumented
line shows one row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from . import documents as stock_documents
from .audit import record
from .models import AuditEvent, GoodsReceipt, StockDocument

ISSUE_PENDING = "issue_pending"
ADDITION_PENDING = "addition_pending"
PERMIT_MISSING = "permit_missing"
RECEIPT_WITHOUT_PERMIT = "receipt_without_permit"

REASON_LABELS = {
    ISSUE_PENDING: _("Issue not approved — it never reaches the issues report"),
    ADDITION_PENDING: _("Addition not approved — the stock was never increased"),
    PERMIT_MISSING: _("Moved with no company voucher number"),
    RECEIPT_WITHOUT_PERMIT: _(
        "Delivered against a purchase order with no company voucher number"
    ),
}

#: Short labels for the table and the tiles. The long sentence above is what the
#: operator reads in the filter and in the spreadsheet; a row needs a badge that
#: fits, not a paragraph that squeezes the columns beside it.
SHORT_REASON_LABELS = {
    ISSUE_PENDING: _("Issue not approved"),
    ADDITION_PENDING: _("Addition not approved"),
    PERMIT_MISSING: _("No voucher number"),
    RECEIPT_WITHOUT_PERMIT: _("Delivery without voucher"),
}

REASON_ORDER = (
    ISSUE_PENDING,
    ADDITION_PENDING,
    PERMIT_MISSING,
    RECEIPT_WITHOUT_PERMIT,
)

#: The reasons a line can be closed from this page by entering a voucher.
PERMIT_REASONS = (PERMIT_MISSING, RECEIPT_WITHOUT_PERMIT)

MAX_PERMIT_LENGTH = 80


@dataclass(frozen=True)
class MissingLine:
    """One undocumented line, with everything the page shows and acts on."""

    reason: str
    occurred_on: date
    document_id: int | None
    receipt_id: int | None
    number: str
    type_label: object
    reference: str
    sku: str
    description: str
    quantity: Decimal
    unit: str
    party: str
    permit: str
    pending: bool

    @property
    def reason_label(self):
        return REASON_LABELS[self.reason]

    @property
    def short_reason_label(self):
        return SHORT_REASON_LABELS[self.reason]

    @property
    def needs_permit(self) -> bool:
        return self.reason in PERMIT_REASONS

    @property
    def action_url(self) -> str:
        if self.receipt_id is not None:
            return f"/reconciliation/receipts/{self.receipt_id}/permit"
        return f"/reconciliation/{self.document_id}/permit"


def parse_filters(params) -> dict:
    """The page's filters: dates, one reason, one site, and a code search."""
    reason = (params.get("reason") or "").strip()
    return {
        "date_from": _as_date(params.get("from")),
        "date_to": _as_date(params.get("to")),
        "reason": reason if reason in REASON_LABELS else "",
        "site": (params.get("site") or "").strip(),
        "query": (params.get("q") or "").strip(),
    }


def _as_date(raw) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def build_rows(**filters) -> list[MissingLine]:
    """Every line whose paperwork is still incomplete, newest first."""
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    reason = filters.get("reason") or ""
    site = filters.get("site") or ""
    query = (filters.get("query") or "").strip().lower()

    rows = _document_rows(date_from, date_to, site) + _receipt_rows(
        date_from, date_to
    )
    if reason:
        rows = [row for row in rows if row.reason == reason]
    if query:
        rows = [
            row
            for row in rows
            if query in row.sku.lower() or query in row.description.lower()
        ]
    rows.sort(key=lambda row: (row.occurred_on, row.number, row.sku), reverse=True)
    return rows


def _document_rows(date_from, date_to, site) -> list[MissingLine]:
    """Documents that moved stock (or claim to) without complete paperwork."""
    queryset = (
        StockDocument.objects.select_related("site")
        .prefetch_related("lines")
        .exclude(status=StockDocument.REJECTED)
    )
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    if site:
        queryset = queryset.filter(site__username=site)

    rows: list[MissingLine] = []
    for document in queryset:
        reason = _reason_for(document)
        if not reason:
            continue
        for line in document.lines.all():
            rows.append(
                MissingLine(
                    reason=reason,
                    occurred_on=document.created_at.date(),
                    document_id=document.pk,
                    receipt_id=None,
                    number=document.number,
                    type_label=document.type_label,
                    reference=document.reference,
                    sku=line.sku,
                    description=line.description,
                    quantity=line.quantity,
                    unit=line.unit,
                    party=document.site.get_username()
                    if document.site_id
                    else document.counterparty,
                    permit=document.external_ref or "",
                    pending=document.status == StockDocument.PENDING,
                )
            )
    return rows


def _reason_for(document: StockDocument) -> str:
    """Why this document is on the page, or "" when its paperwork is complete."""
    if document.status == StockDocument.PENDING:
        return (
            ISSUE_PENDING
            if document.direction == StockDocument.OUT
            else ADDITION_PENDING
        )
    if not (document.external_ref or "").strip():
        return PERMIT_MISSING
    return ""


def _receipt_rows(date_from, date_to) -> list[MissingLine]:
    """Deliveries booked onto the shelf by the receipts screen, unpapered."""
    queryset = (
        GoodsReceipt.objects.prefetch_related("lines")
        .filter(Q(external_ref__isnull=True) | Q(external_ref=""))
        .order_by("-received_at", "-id")
    )
    if date_from:
        queryset = queryset.filter(received_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(received_at__date__lte=date_to)

    receipts = list(queryset)
    covered = _covered_receipt_lines(receipt.po_number for receipt in receipts)

    rows: list[MissingLine] = []
    for receipt in receipts:
        po_key = (receipt.po_number or "").strip().upper()
        for line in receipt.lines.all():
            if (po_key, line.sku) in covered:
                continue
            rows.append(
                MissingLine(
                    reason=RECEIPT_WITHOUT_PERMIT,
                    occurred_on=receipt.received_at.date(),
                    document_id=None,
                    receipt_id=receipt.pk,
                    number=receipt.po_number,
                    type_label=_("Purchase order delivery"),
                    reference=receipt.po_number,
                    sku=line.sku,
                    description=line.description,
                    quantity=line.quantity,
                    unit=line.unit,
                    party=receipt.supplier,
                    permit="",
                    pending=False,
                )
            )
    return rows


def _covered_receipt_lines(po_numbers) -> set[tuple[str, str]]:
    """(PO number, SKU) already documented by an addition for the same order.

    Without this, booking the addition the normal way would leave the delivery
    on the page forever: the same goods would be reported twice.

    The lookup is scoped to the orders on this page — a page load must not walk
    every addition ever booked. It can only ever MISS a coverage (a duplicate
    row), never hide a real gap, because the addition itself is listed when its
    own paperwork is incomplete.
    """
    references = {(number or "").strip() for number in po_numbers}
    references |= {reference.upper() for reference in references}
    references.discard("")
    if not references:
        return set()

    covered: set[tuple[str, str]] = set()
    documents = (
        StockDocument.objects.filter(
            doc_type=StockDocument.PO_RECEIPT, reference__in=sorted(references)
        )
        .exclude(status=StockDocument.REJECTED)
        .prefetch_related("lines")
    )
    for document in documents:
        reference = (document.reference or "").strip().upper()
        if not reference:
            continue
        for line in document.lines.all():
            covered.add((reference, line.sku))
    return covered


def summarize(rows) -> dict:
    """Counts per reason plus the total, for the page header."""
    counts = {reason: 0 for reason in REASON_ORDER}
    for row in rows:
        counts[row.reason] = counts.get(row.reason, 0) + 1
    counts["total"] = len(rows)
    counts["pending"] = sum(1 for row in rows if row.pending)
    return counts


def record_permit(document: StockDocument, external_ref, *, approve=False, user=None):
    """Record the company voucher number, approving the document first if asked.

    The approval happens inside the same transaction: a voucher on a document
    whose stock could not move would claim paper for a movement that never
    happened.
    """
    permit = _clean_permit(external_ref)
    _assert_permit_free(permit, document=document)

    with transaction.atomic():
        if approve and document.status == StockDocument.PENDING:
            document = stock_documents.approve_document(document, user=user)
        document.refresh_from_db()
        document.external_ref = permit
        try:
            document.save(update_fields=["external_ref"])
        except IntegrityError:
            # The check above races another save; the unique index is the referee.
            raise stock_documents.DocumentError(
                _("Voucher %(permit)s was just booked on another document.")
                % {"permit": permit}
            )

    record(
        user=user,
        action=AuditEvent.DOCUMENT_PERMIT,
        entity="stock_document",
        entity_id=document.pk,
        description=f"{document.number} — {permit}",
    )
    return document


def record_receipt_permit(receipt: GoodsReceipt, external_ref, *, user=None):
    """Record the company voucher number of a purchase-order delivery."""
    permit = _clean_permit(external_ref)
    _assert_permit_free(permit, receipt=receipt)

    receipt.external_ref = permit
    try:
        receipt.save(update_fields=["external_ref"])
    except IntegrityError:
        raise stock_documents.DocumentError(
            _("Voucher %(permit)s was just booked on another document.")
            % {"permit": permit}
        )

    record(
        user=user,
        action=AuditEvent.DOCUMENT_PERMIT,
        entity="goods_receipt",
        entity_id=receipt.pk,
        description=f"{receipt.po_number} — {permit}",
    )
    return receipt


def _clean_permit(external_ref) -> str:
    permit = str(external_ref or "").strip()
    if not permit:
        raise stock_documents.DocumentError(_("Enter the company voucher number."))
    if len(permit) > MAX_PERMIT_LENGTH:
        raise stock_documents.DocumentError(
            _("The company voucher number is too long.")
        )
    return permit


def _assert_permit_free(permit: str, *, document=None, receipt=None) -> None:
    """A voucher number is booked once — across documents AND deliveries."""
    taken = StockDocument.objects.filter(external_ref=permit)
    if document is not None:
        taken = taken.exclude(pk=document.pk)
    existing = taken.first()
    if existing is not None:
        raise stock_documents.DocumentError(
            _("Voucher %(permit)s is already booked as %(number)s.")
            % {"permit": permit, "number": existing.number}
        )

    deliveries = GoodsReceipt.objects.filter(external_ref=permit)
    if receipt is not None:
        deliveries = deliveries.exclude(pk=receipt.pk)
    delivery = deliveries.first()
    if delivery is not None:
        raise stock_documents.DocumentError(
            _("Voucher %(permit)s is already recorded on the delivery of %(po)s.")
            % {"permit": permit, "po": delivery.po_number}
        )


def workbook_bytes(rows) -> bytes:
    """The page as a spreadsheet, so the list can be worked outside the app."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Missing paperwork"
    headers = [
        "Date",
        "Reason",
        "Document",
        "Type",
        "PO / reference",
        "Item code",
        "Description",
        "Quantity",
        "Unit",
        "Site / supplier",
        "Company voucher",
    ]
    sheet.append(headers)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="354A5F")
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        sheet.append(
            [
                row.occurred_on.isoformat(),
                str(row.reason_label),
                row.number,
                str(row.type_label),
                row.reference,
                row.sku,
                row.description,
                row.quantity,
                row.unit,
                row.party,
                row.permit,
            ]
        )
    for index, width in enumerate(
        [12, 42, 18, 26, 18, 18, 44, 10, 8, 22, 20], start=1
    ):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
