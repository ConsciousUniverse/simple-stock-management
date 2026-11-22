"""The one definition of the site menu.

Order, grouping and who may see an entry live here rather than in the template,
so the sidebar cannot drift from the URL map: every entry names its URL pattern,
and the active state is derived from the request's resolved URL name instead of
a value each view has to remember to pass.
"""

from dataclasses import dataclass
from typing import Tuple

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class NavItem:
    """One sidebar entry."""

    key: str
    url_name: str
    url: str
    icon: str
    label: object
    manager_only: bool = False


@dataclass(frozen=True)
class NavGroup:
    """A titled block of entries."""

    key: str
    label: object
    items: Tuple[NavItem, ...]


#: Daily work first, administration last: the order a warehouse person reads.
NAV_GROUPS: Tuple[NavGroup, ...] = (
    NavGroup(
        "operations",
        _("Operations"),
        (
            NavItem("dashboard", "index", "/", "i-overview", _("Dashboard")),
            NavItem("items", "stock_page", "/stock/", "i-warehouse", _("Items")),
            NavItem("additions", "receipts_page", "/receipts/", "i-download", _("Additions")),
            NavItem("issues", "issues_page", "/issues/", "i-upload", _("Issues")),
            NavItem("spending", "issues_report", "/issues/report/", "i-data", _("Issues report")),
            NavItem("labels", "print_labels", "/labels/", "i-package", _("Barcode printing")),
            NavItem("reconciliation", "reconciliation_page", "/reconciliation/", "i-alert", _("Missing paperwork")),
        ),
    ),
    NavGroup(
        "admin",
        _("Administration"),
        (
            NavItem("users", "users_page", "/users/", "i-users", _("Users"), manager_only=True),
            NavItem("android", "android_page", "/android/", "i-phone", _("Android app")),
            NavItem("audit", "audit_page", "/audit/", "i-history", _("Audit log"), manager_only=True),
        ),
    ),
)

#: URL name → entry key, so the active entry follows the page being rendered.
URL_SECTIONS = {
    item.url_name: item.key for group in NAV_GROUPS for item in group.items
}


def visible_groups(is_manager: bool) -> Tuple[NavGroup, ...]:
    """The groups this reader may see, with empty groups dropped."""
    groups = []
    for group in NAV_GROUPS:
        items = tuple(
            item for item in group.items if is_manager or not item.manager_only
        )
        if items:
            groups.append(NavGroup(group.key, group.label, items))
    return tuple(groups)
