"""Navigation context for the shell: which entry is current, and who may see it.

The sidebar is built from one place so the active state can never disagree with
the page being rendered: the URL name decides, not a value each view must
remember to pass.
"""

NAV_SECTIONS = {
    "index": "dashboard",
    "stock_page": "items",
    "receipts_page": "additions",
    "issues_page": "issues",
    "issues_report": "spending",
    "print_labels": "labels",
    "users_page": "users",
    "android_page": "android",
    "audit_page": "audit",
}


def navigation(request):
    match = getattr(request, "resolver_match", None)
    user = getattr(request, "user", None)
    is_manager = bool(
        user
        and user.is_authenticated
        and user.groups.filter(name="managers").exists()
    )
    return {
        "section": NAV_SECTIONS.get(getattr(match, "url_name", ""), ""),
        "nav_is_manager": is_manager,
        # The shellbar states the reader's role, so it must be right on every
        # page, not only on the pages whose view happened to pass it.
        "is_manager": is_manager,
    }
