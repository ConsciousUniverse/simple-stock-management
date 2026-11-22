"""The issues report: what left the warehouse, where it went, and who sent it.

The report is built from APPROVED documents only. A pending or rejected
document moved nothing, so counting it would report an issue that never
happened — the same "a sample is not a total" rule the rest of the app
follows.

Dates are inclusive on both ends and are matched on the day the document was
applied, not the day it was typed: a mobile submission approved three days
later belongs to the day the stock actually moved.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO

from django.utils import timezone

from .models import StockDocument

DEFAULT_RANGE_DAYS = 7


def money(value) -> str:
    """Money as the accountant writes it: 6,250.00 (never a locale comma)."""
    return f"{Decimal(value or 0):,.2f}"
MAX_RANGE_DAYS = 366


def _as_date(value, fallback: date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return fallback
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return fallback


def parse_range(raw_from=None, raw_to=None, today: date | None = None):
    """Read the requested window, defaulting to the last week (inclusive)."""
    today = today or timezone.localdate()
    end = _as_date(raw_to, today)
    start = _as_date(raw_from, end - timedelta(days=DEFAULT_RANGE_DAYS - 1))
    if start > end:
        start, end = end, start
    if (end - start).days >= MAX_RANGE_DAYS:
        start = end - timedelta(days=MAX_RANGE_DAYS - 1)
    return start, end


def documents_in_range(date_from: date, date_to: date, *, direction=None, include_pending=False):
    """Approved documents whose stock moved inside the window."""
    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
    end = timezone.make_aware(datetime.combine(date_to, datetime.max.time()))
    queryset = StockDocument.objects.prefetch_related("lines__item", "permits").filter(
        applied_at__gte=start, applied_at__lte=end
    )
    if not include_pending:
        queryset = queryset.filter(status=StockDocument.APPROVED)
    if direction:
        queryset = queryset.filter(direction=direction)
    return queryset.order_by("applied_at", "number")


def build_report(date_from: date, date_to: date, *, doc_types=None):
    """Aggregate the issues in a window: rows plus per-day/site/item totals."""
    queryset = documents_in_range(date_from, date_to, direction=StockDocument.OUT)
    if doc_types:
        queryset = queryset.filter(doc_type__in=doc_types)

    rows = []
    permits: list[dict] = []
    needs_permits: list[dict] = []
    by_day: dict[str, dict] = {}
    by_site: dict[str, dict] = {}
    by_item: dict[str, dict] = {}
    for document in queryset:
        day = timezone.localtime(document.applied_at).date().isoformat()
        destination = _destination(document)
        lines = list(document.lines.all())
        document_permits = list(document.permits.all())
        permit_by_id = {permit.pk: permit for permit in document_permits}
        permit_lines: dict[int, list] = {}
        for line in lines:
            if line.permit_id is not None:
                permit_lines.setdefault(line.permit_id, []).append(line)
        uncovered = [line for line in lines if line.permit_id is None]
        if uncovered:
            needs_permits.append(
                {
                    "id": document.pk,
                    "date": day,
                    "number": document.number,
                    "destination": destination,
                    "type_label": str(document.type_label),
                    "lines": len(lines),
                    "uncovered": len(uncovered),
                    "permit_numbers": ", ".join(
                        permit.permit_no for permit in document_permits
                    ),
                }
            )
        for permit in document_permits:
            permits.append(
                {
                    "date": day,
                    "number": document.number,
                    "doc_type": document.doc_type,
                    "type_label": str(document.type_label),
                    "destination": destination,
                    "permit_no": permit.permit_no,
                    "amount": permit.amount,
                    "amount_display": money(permit.amount),
                    "note": permit.note,
                    "lines": permit_lines.get(permit.pk, []),
                }
            )
        for line in lines:
            unit_price = line.item.retail_price if line.item else Decimal("0.00")
            value = (unit_price or Decimal("0.00")) * line.quantity
            row = {
                "date": day,
                "number": document.number,
                "doc_type": document.doc_type,
                "type_label": str(document.type_label),
                "destination": destination,
                "supplier": document.counterparty,
                "reference": document.reference,
                "sku": line.sku,
                "description": line.description,
                "quantity": line.quantity,
                "unit": line.unit or (line.item.unit if line.item else ""),
                "unit_price": unit_price,
                "value": value,
                "value_display": money(value),
                "issued_by": document.created_by.username if document.created_by else "",
                "approved_by": document.decided_by.username if document.decided_by else "",
                "notes": document.notes,
                "permit_no": (
                    permit_by_id[line.permit_id].permit_no
                    if line.permit_id in permit_by_id
                    else ""
                ),
            }
            rows.append(row)
            _add(by_day, day, row, label=day)
            _add(by_site, destination or "—", row, label=destination or "—")
            _add(by_item, line.sku, row, label=line.sku, extra=line.description)

    total_value = sum((row["value"] for row in rows), Decimal("0.00"))
    permit_total = sum((permit["amount"] for permit in permits), Decimal("0.00"))
    totals = {
        "documents": len({row["number"] for row in rows}),
        "lines": len(rows),
        "quantity": sum(row["quantity"] for row in rows),
        "value": total_value,
        "value_display": money(total_value),
        "permits": len(permits),
        "permit_value": permit_total,
        "permit_value_display": money(permit_total),
        # A line with no permit is the gap the operator chases.
        "uncovered_lines": sum(1 for row in rows if not row["permit_no"]),
    }
    return {
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "permits": permits,
        "needs_permits": needs_permits,
        "totals": totals,
        "by_day": sorted(by_day.values(), key=lambda item: item["label"]),
        "by_site": sorted(by_site.values(), key=lambda item: -item["quantity"]),
        "by_item": sorted(by_item.values(), key=lambda item: -item["quantity"]),
    }


def _destination(document) -> str:
    if document.site_id and document.site:
        return document.site.username
    return document.counterparty


def _add(bucket: dict, key: str, row: dict, *, label: str, extra: str = "") -> None:
    entry = bucket.setdefault(
        key,
        {
            "label": label,
            "description": extra,
            "unit": row.get("unit", ""),
            "documents": set(),
            "lines": 0,
            "quantity": 0,
            "value": Decimal("0.00"),
            "value_display": money(0),
        },
    )
    entry["documents"].add(row["number"])
    entry["lines"] += 1
    entry["quantity"] += row["quantity"]
    entry["value"] += row["value"]
    entry["value_display"] = money(entry["value"])


def workbook_bytes(report) -> bytes:
    """The issues workbook: a detail sheet plus the three roll-ups."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="354A5F")

    def write_sheet(sheet, headers, data, widths):
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        for record in data:
            sheet.append(record)
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        sheet.freeze_panes = "A2"

    detail = workbook.active
    detail.title = "Issues"
    write_sheet(
        detail,
        [
            "Date",
            "Document",
            "Type",
            "Site / project",
            "Supplier",
            "Reference",
            "Item code",
            "Description",
            "Quantity",
            "Unit",
            "Unit price",
            "Value",
            "Issued by",
            "Approved by",
            "Notes",
            "Company permit",
        ],
        [
            [
                row["date"],
                row["number"],
                row["type_label"],
                row["destination"],
                row["supplier"],
                row["reference"],
                row["sku"],
                row["description"],
                row["quantity"],
                row["unit"],
                float(row["unit_price"] or 0),
                float(row["value"] or 0),
                row["issued_by"],
                row["approved_by"],
                row["notes"],
                row.get("permit_no", ""),
            ]
            for row in report["rows"]
        ],
        [12, 16, 26, 22, 22, 16, 18, 40, 10, 8, 12, 14, 14, 14, 30, 18],
    )
    detail.append([])
    detail.append(
        ["Total", "", "", "", "", "", "", "", report["totals"]["quantity"], "", "",
         float(report["totals"]["value"])]
    )

    def rollup(title, key, label_header, with_description=False):
        sheet = workbook.create_sheet(title)
        headers = [label_header]
        if with_description:
            headers.append("Description")
        headers += ["Unit", "Documents", "Lines", "Quantity", "Value"]
        write_sheet(
            sheet,
            headers,
            [
                ([entry["label"]] + ([entry["description"]] if with_description else []))
                + [entry.get("unit", ""), len(entry["documents"]), entry["lines"],
                   entry["quantity"], float(entry["value"])]
                for entry in report[key]
            ],
            [26, 40, 8, 12, 10, 12, 14] if with_description else [26, 8, 12, 10, 12, 14],
        )

    permit_sheet = workbook.create_sheet("Company permits")
    write_sheet(
        permit_sheet,
        ["Date", "Document", "Company permit", "Amount", "Item code", "Description",
         "Quantity", "Unit"],
        [
            [
                permit["date"],
                permit["number"],
                permit["permit_no"],
                float(permit["amount"]),
                line.sku,
                line.description,
                line.quantity,
                line.unit,
            ]
            for permit in report["permits"]
            for line in permit["lines"]
        ],
        [12, 16, 18, 14, 18, 40, 10, 8],
    )

    rollup("By day", "by_day", "Day")
    rollup("By site", "by_site", "Site / project")
    rollup("By item", "by_item", "Item code", with_description=True)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
