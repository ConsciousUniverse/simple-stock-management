"""Who may do what, in one place.

A role check copied into several modules drifts: one copy starts accepting a
second group, or keeps asking about a group that was renamed. Every page and
view imports the same predicate from here.
"""

MANAGER_GROUP = "managers"
SITE_GROUP = "shop_users"


def groups_of(user):
    """The user's group names, as a set (empty for an anonymous visitor)."""
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(user.groups.values_list("name", flat=True))


def is_warehouse_manager(user) -> bool:
    """Managers approve documents; everyone else's entry waits for one."""
    return MANAGER_GROUP in groups_of(user)


def is_site_user(user) -> bool:
    return SITE_GROUP in groups_of(user)
