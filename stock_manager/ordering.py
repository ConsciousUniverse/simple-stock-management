"""One implementation of "sort the table the way the header asks".

The three collections (items, site stock, site requests) share the same
ordering contract: natural sort on the item code, numeric sort on quantities,
case-insensitive text elsewhere, and a stable default so paging does not
shuffle rows between requests. Keeping it in one place means a fix to that
contract cannot land on one table and miss the other two.
"""

from django.db.models import IntegerField
from django.db.models.functions import Cast, Lower
from natsort import natsorted


def apply_ordering(queryset, ordering, *, natural_key, default="-last_updated"):
    """Return ``queryset`` ordered by ``ordering`` (a DRF ``ordering`` param).

    ``natural_key`` extracts the item code from a row, because the site-stock
    and request collections reach it through the related item. The natural sort
    has to happen in Python, so that branch returns a list rather than a
    queryset — the paginator accepts both.
    """
    if not ordering:
        return queryset.order_by(default)

    if ordering.lstrip("-") == "sku":
        return natsorted(
            queryset, key=lambda row: natural_key(row) or "", reverse=ordering.startswith("-")
        )

    if ordering.startswith("-"):
        field = ordering[1:]
        if field == "quantity":
            return queryset.order_by(Cast(field, IntegerField()).desc())
        return queryset.order_by(Lower(field)).reverse()

    if ordering == "quantity":
        return queryset.order_by(Cast(ordering, IntegerField()))
    return queryset.order_by(Lower(ordering))
