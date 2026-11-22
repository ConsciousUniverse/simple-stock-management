"""Why a username cannot sign in right now — and how a manager clears it.

The lockout page tells the person to "ask the system administrator to reset it",
so the reset has to exist in the product. It is computed from the same rows axes
writes, which is what makes the badge on the users page and the action that
clears it two views of one fact instead of two guesses.

A lockout is not an error in the account: the password may be perfectly correct
and the person still cannot get in until the cool-off ends. That distinction is
the whole point of showing it.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def failure_limit():
    """How many failed attempts the lockout allows; 0 means axes never locks."""
    return int(getattr(settings, "AXES_FAILURE_LIMIT", 0) or 0)


def cooloff_hours():
    """Hours until a lockout clears by itself, or None for "until reset"."""
    value = getattr(settings, "AXES_COOLOFF_TIME", None)
    return int(value) if value else None


def _unlocked(limit):
    return {"locked": False, "failures": 0, "limit": limit, "unlocks_at": None}


def _state_of(attempt, limit):
    hours = cooloff_hours()
    unlocks_at = None
    if hours is not None:
        unlocks_at = attempt.attempt_time + timedelta(hours=hours)
    # No cool-off means the lock holds until somebody clears it, so there is no
    # moment to wait for.
    locked = attempt.failures_since_start >= limit and (
        unlocks_at is None or unlocks_at > timezone.now()
    )
    return {
        "locked": locked,
        "failures": attempt.failures_since_start,
        "limit": limit,
        "unlocks_at": unlocks_at if locked else None,
    }


def state(username):
    """The lockout of one username: locked or not, how many failures, until when."""
    from axes.models import AccessAttempt

    limit = failure_limit()
    if not username or not limit:
        return _unlocked(limit)
    attempt = (
        AccessAttempt.objects.filter(username__iexact=username)
        .order_by("-attempt_time")
        .first()
    )
    return _state_of(attempt, limit) if attempt else _unlocked(limit)


def states(usernames):
    """The same answer for a page of accounts, in ONE query.

    One query per row is how a list page turns into a slow page; the page asks
    for every account it is about to render.
    """
    from axes.models import AccessAttempt

    limit = failure_limit()
    wanted = [name for name in usernames if name]
    answers = {name: _unlocked(limit) for name in wanted}
    if not wanted or not limit:
        return answers

    # ``__in`` is case-sensitive on Postgres, so the spellings that could hold
    # the row are all asked for in the one query.
    spellings = set(wanted) | {name.lower() for name in wanted}
    latest = {}
    rows = (
        AccessAttempt.objects.filter(username__in=spellings)
        .order_by("username", "-attempt_time")
    )
    for row in rows:
        latest.setdefault((row.username or "").lower(), row)

    for name in wanted:
        attempt = latest.get(name.lower())
        if attempt is not None:
            answers[name] = _state_of(attempt, limit)
    return answers


def clear(username):
    """Remove the failed attempts of one username. Returns how many rows went.

    Deletes the same rows ``state()`` reads, so the badge and the button can
    never disagree about whether a lock is gone.
    """
    from axes.models import AccessAttempt

    if not username:
        return 0
    deleted, _ = AccessAttempt.objects.filter(username__iexact=username).delete()
    return deleted
