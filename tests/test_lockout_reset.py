"""The lockout page promises a reset; the reset has to exist.

``axes`` locks a username after too many failed attempts, and the page told the
person to "ask the system administrator to reset it" — with no reset anywhere in
the product. The badge on the users page and the button that clears it read the
same rows, so they cannot disagree.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from axes.models import AccessAttempt

from stock_manager import lockout
from stock_manager.models import AuditEvent

pytestmark = pytest.mark.django_db

LIMIT = 3  # settings_test: AXES_FAILURE_LIMIT = 3, AXES_COOLOFF_TIME = 1 hour


def _attempt(username, failures, when=None):
    attempt = AccessAttempt.objects.create(
        user_agent="pytest",
        username=username,
        http_accept="",
        path_info="/accounts/login/",
        get_data="",
        post_data="",
        failures_since_start=failures,
    )
    if when is not None:
        # ``attempt_time`` is auto_now_add, so the age is set after the insert.
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=when)
        attempt.refresh_from_db()
    return attempt


class TestTheState:
    def test_under_the_limit_is_not_locked(self):
        _attempt("lifeendy", LIMIT - 1)
        assert lockout.state("lifeendy")["locked"] is False

    def test_at_the_limit_is_locked_with_a_time_it_clears(self):
        _attempt("lifeendy", LIMIT)

        state = lockout.state("lifeendy")

        assert state["locked"] is True
        assert state["failures"] == LIMIT
        assert state["unlocks_at"] > timezone.now()

    def test_an_expired_lock_is_not_a_lock(self):
        _attempt("lifeendy", LIMIT, when=timezone.now() - timedelta(hours=2))
        assert lockout.state("lifeendy")["locked"] is False

    def test_a_username_that_never_failed_is_not_locked(self):
        assert lockout.state("nobody") == {
            "locked": False,
            "failures": 0,
            "limit": LIMIT,
            "unlocks_at": None,
        }

    def test_without_a_limit_axes_never_locks(self, settings):
        settings.AXES_FAILURE_LIMIT = 0
        _attempt("lifeendy", 50)
        assert lockout.state("lifeendy")["locked"] is False


class TestTheManagerCanClearIt:
    def test_the_page_shows_the_lock_and_the_button(self, client, manager):
        User.objects.create_user(username="lifeendy", password="x-pass-1234")
        _attempt("lifeendy", LIMIT)
        client.force_login(manager)

        body = client.get("/users/").content.decode()

        assert "Clear the lockout" in body

    def test_clearing_it_removes_the_attempts_and_is_audited(self, client, manager):
        _attempt("lifeendy", LIMIT)
        target = User.objects.create_user(username="lifeendy", password="x-pass-1234")
        client.force_login(manager)

        response = client.post(
            "/users/", {"action": "unlock", "user_id": target.pk}, follow=True
        )

        assert lockout.state("lifeendy")["locked"] is False
        assert AccessAttempt.objects.filter(username="lifeendy").count() == 0
        entry = AuditEvent.objects.filter(action=AuditEvent.USER_UNLOCKED).first()
        assert entry is not None and "lifeendy" in entry.description
        assert "cleared" in response.content.decode()

    def test_clearing_one_account_leaves_the_other_alone(self, client, manager):
        _attempt("lifeendy", LIMIT)
        _attempt("someone", LIMIT)
        target = User.objects.create_user(username="lifeendy", password="x-pass-1234")
        client.force_login(manager)

        client.post("/users/", {"action": "unlock", "user_id": target.pk}, follow=True)

        assert lockout.state("someone")["locked"] is True

    def test_a_missing_account_is_refused(self, client, manager):
        client.force_login(manager)

        response = client.post(
            "/users/", {"action": "unlock", "user_id": "999999"}, follow=True
        )

        assert "does not exist" in response.content.decode()


class TestThePageAsksOnce:
    def test_every_row_is_answered_from_one_query(self, client, manager):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for name in ("a", "b", "c"):
            User.objects.create_user(username=name, password="x-pass-1234")
            _attempt(name, LIMIT)
        client.force_login(manager)

        with CaptureQueriesContext(connection) as queries:
            response = client.get("/users/")

        # Three locked accounts must not cost three lockout queries: the page
        # asks once for all of them.
        attempt_queries = [q for q in queries if "axes_accessattempt" in q["sql"]]
        assert len(attempt_queries) == 1
        assert response.content.decode().count("Clear the lockout") == 3
