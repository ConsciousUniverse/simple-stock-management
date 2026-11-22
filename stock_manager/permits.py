"""Company permits: one issue, several permits, each with its own lines.

The operator's rule: an issue dated 1/7 may be paid against the company permits
050340604, 0503537228 and 05245322, and each permit names the items it covers.
The paper is therefore per LINE, not per document — the same rule the missing
paperwork page follows — and a document is documented only when every one of its
lines belongs to a permit.

A permit belongs to exactly one document (its number is unique across all of
them), because the company's permit is written against one issue.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from .audit import record
from .models import AuditEvent, DocumentPermit, StockDocument

MAX_PERMIT_LENGTH = 80
MAX_PERMITS = 20


class PermitError(Exception):
    """Something the operator can fix: a blank number, a duplicate, a bad amount."""


def _money(value) -> str:
    return f"{Decimal(value or 0):,.2f}"


def format_amount(value) -> str:
    """Money as the accountant writes it: 6,250.00, in either language.

    Django's own number formatting switches to the Arabic decimal comma, and an
    accountant comparing this page with the company's paper needs the same
    figure everywhere.
    """
    return _money(value)


def parse_form(form, line_ids) -> tuple[list[dict], dict[str, str]]:
    """Read the permit rows and the lines each one covers.

    The fields are indexed (``permit_no_0``, ``items_0``) so a permit and its
    items stay together even when a row in the middle is left blank. A line
    ticked under two permits is refused rather than guessed: the paper says one
    permit covers it, and the warehouse cannot decide which.
    """
    rows: list[dict] = []
    assignments: dict[str, str] = {}
    for index in range(MAX_PERMITS):
        number = str(form.get(f"permit_no_{index}") or "").strip()
        raw_amount = form.get(f"permit_amount_{index}") or ""
        note = str(form.get(f"permit_note_{index}") or "").strip()
        selected = [
            value for value in form.getlist(f"items_{index}") if str(value) in line_ids
        ]
        if not number and not str(raw_amount).strip() and not note and not selected:
            continue

        rows.append({"permit_no": number, "amount": raw_amount, "note": note})
        for line_id in selected:
            if line_id in assignments:
                raise PermitError(
                    _("Line %(line)s is ticked under more than one permit.")
                    % {"line": line_id}
                )
            assignments[line_id] = number
    return rows, assignments


#: A thousands separator, and only that: 1,250.50. A comma used as a decimal
#: separator (1.250,50 or the Arabic 1250,50) is NOT stripped — reading it as a
#: separator turns 1250,50 into 125050, a silent 100x inflation.
THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")


def _amount(raw) -> Decimal:
    text = str(raw or "").strip()
    if not text:
        return Decimal("0.00")
    if "," in text:
        if not THOUSANDS.match(text):
            raise PermitError(_("Enter the permit amount as a number."))
        text = text.replace(",", "")
    try:
        value = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise PermitError(_("Enter the permit amount as a number."))
    if value < 0:
        raise PermitError(_("The permit amount cannot be negative."))
    return value


def _validate(document, rows) -> list[dict]:
    if len(rows) > MAX_PERMITS:
        raise PermitError(
            _("A document takes at most %(max)s company permits.") % {"max": MAX_PERMITS}
        )

    seen: set[str] = set()
    cleaned = []
    for row in rows:
        number = row["permit_no"]
        if not number:
            raise PermitError(_("Enter the permit number, or clear the row."))
        if len(number) > MAX_PERMIT_LENGTH:
            raise PermitError(_("The permit number is too long."))
        if number in seen:
            raise PermitError(
                _("Permit %(permit)s is listed twice on this document.")
                % {"permit": number}
            )
        seen.add(number)

        other = (
            DocumentPermit.objects.filter(permit_no=number)
            .exclude(document=document)
            .select_related("document")
            .first()
        )
        if other is not None:
            raise PermitError(
                _("Permit %(permit)s is already recorded on %(number)s.")
                % {"permit": number, "number": other.document.number}
            )

        cleaned.append({**row, "amount": _amount(row["amount"])})
    return cleaned


def save_permits(document: StockDocument, rows, assignments, *, user=None):
    """Replace the document's permits and the line they cover.

    ``assignments`` maps a line id to a permit number ("" clears it). Removing a
    permit detaches its lines instead of deleting them: the stock moved, only
    the paper changed.
    """
    cleaned = _validate(document, rows)

    try:
        with transaction.atomic():
            existing = {permit.permit_no: permit for permit in document.permits.all()}
            kept: set[str] = set()
            for row in cleaned:
                permit = existing.get(row["permit_no"])
                if permit is None:
                    DocumentPermit.objects.create(
                        document=document,
                        permit_no=row["permit_no"],
                        amount=row["amount"],
                        note=row["note"],
                        created_by=user,
                    )
                else:
                    permit.amount = row["amount"]
                    permit.note = row["note"]
                    permit.save(update_fields=["amount", "note"])
                kept.add(row["permit_no"])

            for number, permit in existing.items():
                if number not in kept:
                    permit.delete()

            by_number = {
                permit.permit_no: permit for permit in document.permits.all()
            }
            for line in document.lines.all():
                wanted = str(assignments.get(str(line.pk)) or "").strip()
                if wanted and wanted not in by_number:
                    raise PermitError(
                        _("Choose a permit of this document for %(sku)s.")
                        % {"sku": line.sku}
                    )
                permit = by_number.get(wanted)
                permit_id = permit.pk if permit is not None else None
                if line.permit_id != permit_id:
                    line.permit = permit
                    line.save(update_fields=["permit"])
    except IntegrityError:
        # Two operators saving the same number at once: the unique index is the
        # referee, and the message must say so rather than show a database error.
        raise PermitError(_("That permit number was just recorded elsewhere."))

    record(
        user=user,
        action=AuditEvent.DOCUMENT_PERMIT,
        entity="stock_document",
        entity_id=document.pk,
        description=_describe(document, cleaned),
    )
    return document


def _describe(document, rows) -> str:
    if not rows:
        return f"{document.number} — " + str(_("permits cleared"))
    parts = [
        f"{row['permit_no']} ({_money(row['amount'])})" for row in rows
    ]
    return f"{document.number} — " + ", ".join(parts)


def line_value(line) -> Decimal:
    """What a line is worth at the catalogue price, as the report values it."""
    price = line.item.retail_price if line.item is not None else Decimal("0.00")
    return (price or Decimal("0.00")) * line.quantity


def coverage(document) -> dict:
    """What the permits account for, and what is still uncovered."""
    lines = list(document.lines.select_related("item").all())
    permits = list(document.permits.all())

    total = sum((line_value(line) for line in lines), Decimal("0.00"))
    uncovered = [line for line in lines if line.permit_id is None]
    covered = [line for line in lines if line.permit_id is not None]
    uncovered_value = sum((line_value(line) for line in uncovered), Decimal("0.00"))
    permit_total = sum((permit.amount for permit in permits), Decimal("0.00"))

    return {
        "lines": len(lines),
        "covered_lines": len(covered),
        "uncovered_lines": len(uncovered),
        "value": total,
        "value_display": _money(total),
        "uncovered_value": uncovered_value,
        "uncovered_value_display": _money(uncovered_value),
        "permit_total": permit_total,
        "permit_total_display": _money(permit_total),
        "difference": permit_total - total,
        "difference_display": _money(permit_total - total),
        "documented": bool(permits) and not uncovered,
        "permits": permits,
    }


def permits_for(documents) -> dict[int, list[DocumentPermit]]:
    """Permits of the given documents, each with its lines, in one query."""
    ids = [document.pk for document in documents]
    if not ids:
        return {}
    grouped: dict[int, list[DocumentPermit]] = {}
    permits = DocumentPermit.objects.filter(document_id__in=ids).prefetch_related(
        "lines"
    )
    for permit in permits:
        grouped.setdefault(permit.document_id, []).append(permit)
    return grouped


def permit_numbers(document) -> str:
    return ", ".join(permit.permit_no for permit in document.permits.all())

def submitted_rows(form) -> list[dict]:
    """The rows exactly as posted, so a failed save can be shown again."""
    rows = []
    for index in range(MAX_PERMITS):
        number = str(form.get(f"permit_no_{index}") or "").strip()
        raw_amount = form.get(f"permit_amount_{index}") or ""
        note = str(form.get(f"permit_note_{index}") or "").strip()
        if not number and not str(raw_amount).strip() and not note:
            continue
        rows.append({"permit_no": number, "amount": raw_amount, "note": note})
    return rows


def submitted_items(form, line_ids) -> dict[str, str]:
    """Which permit each posted item was ticked under."""
    assignments: dict[str, str] = {}
    for index in range(MAX_PERMITS):
        number = str(form.get(f"permit_no_{index}") or "").strip()
        for line_id in form.getlist(f"items_{index}"):
            if str(line_id) in line_ids:
                assignments[str(line_id)] = number
    return assignments
