"""Stock documents: the one place a stock movement is created and applied.

Every addition (PO receipt, transfer in from another project, return from a
site) and every issue (issue to a site, transfer out to another project,
return/rejection to a supplier) is a :class:`StockDocument`. The document is
the audit record; the movement happens exactly once, in :func:`_apply`, and
only for an APPROVED document.

Two rules this module exists to enforce:

* **A mobile submission moves nothing.** Documents created from the Android
  app are ``pending`` until a warehouse manager approves them on the web.
* **A voucher is booked once.** ``external_ref`` is the company voucher
  number; a repeated mobile retry or an import of the same voucher is refused
  instead of deducting the quantity a second time.
"""

from __future__ import annotations

import re
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .audit import record
from .models import AuditEvent, Item, ShopItem, StockDocument, StockDocumentLine

IN = StockDocument.IN
OUT = StockDocument.OUT

TYPE_DIRECTION = {
    StockDocument.PO_RECEIPT: IN,
    StockDocument.PROJECT_TRANSFER_IN: IN,
    StockDocument.SITE_RETURN: IN,
    StockDocument.SITE_ISSUE: OUT,
    StockDocument.PROJECT_TRANSFER_OUT: OUT,
    StockDocument.SUPPLIER_RETURN: OUT,
}

# Types that move stock to or from a site's own stock as well as the warehouse.
SITE_TYPES = (StockDocument.SITE_ISSUE, StockDocument.SITE_RETURN)
# Types where a counterparty name is required (supplier, or the other project).
COUNTERPARTY_REQUIRED = (
    StockDocument.PO_RECEIPT,
    StockDocument.PROJECT_TRANSFER_IN,
    StockDocument.PROJECT_TRANSFER_OUT,
    StockDocument.SUPPLIER_RETURN,
)

MAX_NUMBER_ATTEMPTS = 5

#: A photographed voucher: big enough for a readable A4 sheet, small enough
#: that a phone on a bad line is not stuck for minutes. The app compresses
#: before sending; this is the server's own ceiling, so a hand-rolled client
#: cannot fill the database with camera originals.
MAX_PHOTO_BYTES = 6 * 1024 * 1024
PHOTO_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic")


# Offered as suggestions in the unit box. Free text is allowed: the catalogue
# mixes Arabic and English articles and a unit is data, not an enum.
COMMON_UNITS = [
    "قطعة", "متر", "كجم", "لفة", "كرتونة", "لتر", "عبوة", "طن", "متر مربع",
    "PCS", "MTR", "KG", "ROLL", "BOX", "LTR", "SET",
]


class DocumentError(ValueError):
    """A refusal the operator can act on (never an internal error)."""


def direction_of(doc_type: str) -> str:
    try:
        return TYPE_DIRECTION[doc_type]
    except KeyError:
        raise DocumentError(f"Unknown document type: {doc_type}")


def parse_lines(raw_lines) -> list[tuple[str, int, str, str]]:
    """Normalise submitted lines into ``[(sku, quantity, description)]``.

    A repeated SKU is summed, so a double-submitted line cannot be booked
    twice, and a line without a quantity is refused rather than dropped: a
    silently dropped line is a document that lies about what it moved.
    """
    merged: dict[str, tuple[int, str, str]] = {}
    for raw in raw_lines or []:
        if not isinstance(raw, dict):
            raise DocumentError("Each line must be an item and a quantity.")
        sku = str(raw.get("sku") or "").strip()
        if not sku:
            continue
        try:
            quantity = int(str(raw.get("quantity")))
        except (TypeError, ValueError):
            raise DocumentError("The quantity must be a whole number.")
        if quantity <= 0:
            raise DocumentError("The quantity must be greater than zero.")
        description = str(raw.get("description") or "").strip()
        unit = str(raw.get("unit") or "").strip()[:20]
        if sku in merged:
            merged[sku] = (
                merged[sku][0] + quantity,
                merged[sku][1] or description,
                merged[sku][2] or unit,
            )
        else:
            merged[sku] = (quantity, description, unit)
    if not merged:
        raise DocumentError("Add at least one item.")
    return [(sku, qty, desc, unit) for sku, (qty, desc, unit) in merged.items()]


def find_item_by_code(code: str) -> Item | None:
    """The item a scanned label points at.

    A label carries the SKU (``barcodes.py``), but a scanner may add spaces or
    change the case, and an operator may type the code by hand. The exact key
    is tried first; failing that, spaces/dashes/underscores are ignored on both
    sides — ``CBL 3X25`` and ``CBL-3X25`` are the same article — with the scan
    bounded by a prefix so a lookup never walks the whole catalogue.
    """
    raw = (code or "").strip()
    if not raw:
        return None
    item = Item.objects.filter(pk=raw).first()
    if item is not None:
        return item
    item = Item.objects.filter(sku__iexact=raw).first()
    if item is not None:
        return item

    def loose(value):
        return re.sub(r"[\s\-_]", "", value or "").upper()

    wanted = loose(raw)
    head = loose(raw.split()[0].split("-")[0])[:6]
    if not wanted or not head.isalnum():
        return None
    for candidate in Item.objects.filter(sku__istartswith=head)[:500]:
        if loose(candidate.sku) == wanted:
            return candidate
    return None


def check_photo(data, content_type: str = "", name: str = ""):
    """Refuse a voucher photo that cannot be read later, and say why."""
    if not data:
        raise DocumentError("صوّر المستند أولًا: لا يمكن اعتماد مستند بلا صورته.")
    if len(data) > MAX_PHOTO_BYTES:
        raise DocumentError(
            "صورة المستند أكبر من المسموح (٦ ميجابايت). صوّرها بدقة أقل."
        )
    kind = (content_type or "").split(";")[0].strip().lower()
    if kind and kind not in PHOTO_TYPES:
        raise DocumentError("صيغة صورة المستند غير مدعومة (JPG أو PNG).")
    return data


def _next_number(doc_type: str) -> str:
    prefix = "RCV" if direction_of(doc_type) == IN else "ISS"
    year = timezone.localdate().year
    stem = f"{prefix}-{year}-"
    last = (
        StockDocument.objects.filter(number__startswith=stem)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    sequence = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{stem}{sequence:04d}"


def _existing_by_reference(external_ref: str):
    return StockDocument.objects.filter(external_ref=external_ref).first()


def create_document(
    *,
    doc_type: str,
    lines,
    site=None,
    counterparty: str = "",
    reference: str = "",
    external_ref: str | None = None,
    notes: str = "",
    created_by=None,
    source: str = StockDocument.WEB,
    pending: bool | None = None,
    document_date=None,
    location: str = "",
    engineer_name: str = "",
    photo=None,
    photo_type: str = "",
    photo_name: str = "",
) -> StockDocument:
    """Create a document and, when it is a web entry, apply it immediately.

    ``pending`` defaults to False for the web (a manager is entering it) and
    True for the mobile app, so a phone submission can never move stock.
    """
    if doc_type not in TYPE_DIRECTION:
        raise DocumentError("Unknown document type.")
    direction = direction_of(doc_type)
    counterparty = (counterparty or "").strip()
    reference = (reference or "").strip()
    external_ref = (external_ref or "").strip() or None
    location = (location or "").strip()[:200]
    engineer_name = (engineer_name or "").strip()[:120]

    # A site account OR a written location: the voucher names the place, and
    # requiring a registered account would refuse a real permit typed by hand.
    if doc_type in SITE_TYPES and site is None and not location:
        raise DocumentError("Choose the site for this document.")
    if doc_type in COUNTERPARTY_REQUIRED and not counterparty:
        raise DocumentError("Enter the supplier or project name.")

    parsed = parse_lines(lines)
    if pending is None:
        pending = source != StockDocument.WEB

    # An issue is checked against the shelf NOW, so the operator reads the
    # shortage while holding the phone instead of after a manager approves it.
    # ``_apply`` re-checks inside the conditional UPDATE — this is the message,
    # that is the guarantee.
    if direction == OUT:
        for sku, quantity, _description, _unit in parsed:
            item = _item_for_line(sku)
            available = item.quantity if item is not None else 0
            if item is None or quantity > available:
                unit = (item.unit if item is not None else "") or ""
                raise DocumentError(
                    f"لا يمكن صرف {quantity} {unit} من {sku} — "
                    f"المتاح في المخزن {available} {unit}".rstrip()
                )

    if external_ref:
        existing = _existing_by_reference(external_ref)
        if existing:
            raise DocumentError(
                f"Voucher {external_ref} is already booked as {existing.number}; "
                "the quantity was not counted twice."
            )

    with transaction.atomic():
        document = _insert_document(
            doc_type=doc_type,
            direction=direction,
            site=site,
            counterparty=counterparty,
            reference=reference,
            external_ref=external_ref,
            notes=notes,
            created_by=created_by,
            source=source,
            pending=pending,
        )
        if photo:
            document.photo = photo
            document.photo_type = (photo_type or "image/jpeg")[:60]
            document.photo_name = (photo_name or "voucher.jpg")[:120]
            document.photo_uploaded_at = timezone.now()
        document.document_date = document_date
        document.location = location
        document.engineer_name = engineer_name
        document.save(
            update_fields=[
                "photo",
                "photo_type",
                "photo_name",
                "photo_uploaded_at",
                "document_date",
                "location",
                "engineer_name",
            ]
        )
        for sku, quantity, description, unit in parsed:
            item = _item_for_line(sku)
            StockDocumentLine.objects.create(
                document=document,
                item=item,
                sku=sku,
                description=description or (item.description if item else sku),
                quantity=quantity,
                # The line states its own unit; an unstated one comes from the
                # catalogue at the moment of booking (a snapshot, not a join).
                unit=unit or (item.unit if item else ""),
            )
        if not pending:
            _apply(document, approved_by=created_by)
    document.refresh_from_db()
    # Recorded after the transaction: a failed audit write must not roll back a
    # document that was saved correctly.
    record(
        user=created_by,
        action=AuditEvent.DOCUMENT_CREATED,
        entity="stock_document",
        entity_id=document.pk,
        description=_describe(document),
    )
    return document


def _describe(document) -> str:
    """A one-line, language-neutral summary for the audit trail."""
    lines = list(document.lines.all())
    shown = "، ".join(
        f"{line.sku} ×{line.quantity}{(' ' + line.unit) if line.unit else ''}"
        for line in lines[:3]
    )
    more = f" (+{len(lines) - 3})" if len(lines) > 3 else ""
    parts = [document.number, document.get_doc_type_display()]
    if document.counterparty:
        parts.append(document.counterparty)
    if document.site_id:
        parts.append(document.site.get_username())
    return " · ".join(str(part) for part in parts) + (f" — {shown}{more}" if shown else "")


def _insert_document(**kwargs) -> StockDocument:
    """Insert with a unique document number, retrying on a numbering race."""
    pending = kwargs.pop("pending")
    status = StockDocument.PENDING if pending else StockDocument.APPROVED
    for attempt in range(MAX_NUMBER_ATTEMPTS):
        try:
            with transaction.atomic():
                return StockDocument.objects.create(
                    number=_next_number(kwargs["doc_type"]),
                    status=status,
                    **kwargs,
                )
        except IntegrityError:
            if attempt == MAX_NUMBER_ATTEMPTS - 1:
                raise
    raise DocumentError("Could not allocate a document number.")


def _item_for_line(sku: str) -> Item | None:
    """The existing item, or None: an unknown SKU is only created by _apply."""
    return Item.objects.filter(pk=sku).first()


def approve_document(document: StockDocument, user=None, note: str = "") -> StockDocument:
    """Approve a pending document and move the stock, exactly once."""
    with transaction.atomic():
        locked = StockDocument.objects.select_for_update().get(pk=document.pk)
        if locked.status == StockDocument.APPROVED:
            raise DocumentError("This document is already approved.")
        if locked.status == StockDocument.REJECTED:
            raise DocumentError("A rejected document cannot be approved.")
        _apply(locked, approved_by=user, note=note)
        locked.refresh_from_db()
    record(
        user=user,
        action=AuditEvent.DOCUMENT_APPROVED,
        entity="stock_document",
        entity_id=locked.pk,
        description=_describe(locked),
    )
    return locked


def reject_document(document: StockDocument, user=None, note: str = "") -> StockDocument:
    """Reject a pending document: nothing moves, and it never will."""
    with transaction.atomic():
        locked = StockDocument.objects.select_for_update().get(pk=document.pk)
        if locked.status != StockDocument.PENDING:
            raise DocumentError("Only a pending document can be rejected.")
        locked.status = StockDocument.REJECTED
        locked.decided_by = user
        locked.decided_at = timezone.now()
        locked.decision_note = (note or "").strip()
        locked.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    record(
        user=user,
        action=AuditEvent.DOCUMENT_REJECTED,
        entity="stock_document",
        entity_id=locked.pk,
        description=_describe(locked)
        + (f" — {locked.decision_note}" if locked.decision_note else ""),
    )
    return locked


def _apply(document: StockDocument, approved_by=None, note: str = "") -> None:
    """Move the stock for an approved document.

    Called inside a transaction. The warehouse decrement is a conditional
    UPDATE (``quantity >= qty``), so two approvals can never oversell.
    """
    if document.applied_at is not None:
        raise DocumentError("This document has already been applied.")

    incoming = document.direction == IN
    for line in document.lines.select_related("item"):
        item = line.item
        if incoming:
            item, _ = Item.objects.get_or_create(
                pk=line.sku,
                defaults={
                    "description": line.description or line.sku,
                    "retail_price": Decimal("0.00"),
                    "quantity": 0,
                },
            )
            if not line.item_id:
                line.item = item
                line.save(update_fields=["item"])
            if line.unit and not item.unit:
                # An addition is where a new article's unit is first learned.
                Item.objects.filter(pk=item.pk).update(unit=line.unit)
                item.refresh_from_db(fields=["unit"])
            Item.objects.filter(pk=item.pk).update(
                quantity=F("quantity") + line.quantity
            )
        else:
            if item is None:
                raise DocumentError(f"Item {line.sku} is not in the warehouse.")
            updated = Item.objects.filter(
                pk=item.pk, quantity__gte=line.quantity
            ).update(quantity=F("quantity") - line.quantity)
            if not updated:
                item.refresh_from_db()
                raise DocumentError(
                    f"Not enough stock for {line.sku}: "
                    f"{item.quantity} available, {line.quantity} requested."
                )

        if document.doc_type in SITE_TYPES and document.site_id:
            _move_site_stock(document, line, incoming)

    document.status = StockDocument.APPROVED
    document.applied_at = timezone.now()
    if approved_by is not None:
        document.decided_by = approved_by
    document.decided_at = document.decided_at or timezone.now()
    if note:
        document.decision_note = note.strip()
    document.save(
        update_fields=[
            "status",
            "applied_at",
            "decided_by",
            "decided_at",
            "decision_note",
        ]
    )


def _move_site_stock(document: StockDocument, line, incoming: bool) -> None:
    """Mirror the movement on the site's own stock (issue in, return out)."""
    item = Item.objects.filter(pk=line.sku).first()
    if item is None:
        return
    site_item, _ = ShopItem.objects.get_or_create(
        shop_user_id=document.site_id, item=item, defaults={"quantity": 0}
    )
    if incoming:  # site_return: the site gives the goods back
        updated = ShopItem.objects.filter(
            pk=site_item.pk, quantity__gte=line.quantity
        ).update(quantity=F("quantity") - line.quantity)
        if not updated:
            site_item.refresh_from_db()
            raise DocumentError(
                f"The site holds only {site_item.quantity} of {line.sku}."
            )
    else:  # site_issue
        ShopItem.objects.filter(pk=site_item.pk).update(
            quantity=F("quantity") + line.quantity
        )
