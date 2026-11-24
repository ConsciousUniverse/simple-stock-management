"""One internal code over several Oracle item codes.

Oracle can carry the same physical article under more than one item code. The
warehouse reads one balance for it, so several ``Item`` rows may share an
``ItemGroup``. Nothing about a movement changes: a document line still names the
Oracle code that is on the paper, and the quantity stays on that row. The group
total is a sum over the member rows — computed on read, never stored, so the same
quantity cannot be counted twice.
"""

from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.utils.translation import gettext as _

from . import audit
from .models import AuditEvent, Item, ItemGroup


class ItemCodeError(ValueError):
    """A refusal the operator can act on (never an internal error)."""


def _codes(skus):
    cleaned = []
    for raw in skus or []:
        sku = str(raw or "").strip()
        if sku and sku not in cleaned:
            cleaned.append(sku)
    if not cleaned:
        raise ItemCodeError(_("Choose at least one Oracle code."))
    return cleaned


def groups_overview():
    """Every internal code with its member Oracle codes and summed quantity."""
    groups = (
        ItemGroup.objects.annotate(
            total_quantity=Sum("items__quantity", filter=Q(items__is_active=True)),
            member_count=Count("items", filter=Q(items__is_active=True)),
        )
        .filter(member_count__gt=0)
        .prefetch_related(
            Prefetch("items", queryset=Item.objects.filter(is_active=True))
        )
        .order_by("code")
    )
    return [
        {
            "code": group.code,
            "items": sorted(group.items.all(), key=lambda item: item.sku),
            "total_quantity": group.total_quantity or 0,
            "member_count": group.member_count,
        }
        for group in groups
    ]


def group_totals():
    """``{internal code: summed quantity}`` in one query."""
    return {
        row["internal_group__code"]: row["total"]
        for row in Item.objects.filter(
            internal_group__isnull=False, is_active=True
        )
        .values("internal_group__code")
        .annotate(total=Sum("quantity"))
    }


def _target_group(target_code):
    target_code = (target_code or "").strip()
    if not target_code:
        return ItemGroup.create_next()
    group = ItemGroup.objects.filter(code=target_code).first()
    if group is None:
        raise ItemCodeError(
            _("The internal code %(code)s does not exist.") % {"code": target_code}
        )
    return group


def _drop_empty(groups):
    for group in groups:
        if group is not None and not group.items.exists():
            group.delete()


def merge_codes(skus, target_code="", user=None):
    """Put the selected Oracle codes under one internal code.

    An empty ``target_code`` creates a new internal code; an existing one moves
    the codes into it. Quantities and documents are not touched.
    """
    codes = _codes(skus)
    with transaction.atomic():
        items = list(Item.objects.select_for_update().filter(sku__in=codes))
        found = {item.sku for item in items}
        missing = [code for code in codes if code not in found]
        if missing:
            raise ItemCodeError(
                _("Unknown codes: %(codes)s") % {"codes": "، ".join(missing)}
            )

        group = _target_group(target_code)
        previous = {
            item.internal_group
            for item in items
            if item.internal_group_id and item.internal_group_id != group.pk
        }
        for item in items:
            if item.internal_group_id != group.pk:
                item.internal_group = group
                item.save(update_fields=["internal_group"])
        _drop_empty(previous)

    audit.record(
        user=user,
        action=AuditEvent.ITEM_GROUPED,
        entity="item_group",
        entity_id=group.code,
        description=f"{group.code} ← " + "، ".join(codes),
    )
    return group


def move_code(sku, target_code="", user=None):
    """Move one Oracle code to another internal code (or a new one)."""
    sku = str(sku or "").strip()
    if not sku:
        raise ItemCodeError(_("Choose an Oracle code."))

    with transaction.atomic():
        item = Item.objects.select_for_update().filter(sku=sku).first()
        if item is None:
            raise ItemCodeError(_("The code %(sku)s does not exist.") % {"sku": sku})
        previous = item.internal_group

        group = _target_group(target_code)
        if previous is not None and previous.pk == group.pk:
            return group

        item.internal_group = group
        item.save(update_fields=["internal_group"])
        _drop_empty([previous])

    audit.record(
        user=user,
        action=AuditEvent.ITEM_UNGROUPED,
        entity="item",
        entity_id=sku,
        description=f"{sku}: {previous.code if previous else '—'} → {group.code}",
    )
    return group
