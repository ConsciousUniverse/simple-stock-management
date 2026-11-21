"""Shell context: the menu, the current entry, and who the reader is.

The sidebar is built from :mod:`stock_manager.navigation` so the order and the
active state can never disagree with the page being rendered: the URL name
decides, not a value each view must remember to pass.
"""

from .navigation import URL_SECTIONS, visible_groups
from .permissions import is_warehouse_manager


def navigation(request):
    match = getattr(request, "resolver_match", None)
    user = getattr(request, "user", None)
    manager = is_warehouse_manager(user) if user is not None else False
    return {
        "nav_groups": visible_groups(manager),
        "section": URL_SECTIONS.get(getattr(match, "url_name", ""), ""),
        "nav_is_manager": manager,
        # The shellbar states the reader's role, so it must be right on every
        # page, not only on the pages whose view happened to pass it.
        "is_manager": manager,
    }
