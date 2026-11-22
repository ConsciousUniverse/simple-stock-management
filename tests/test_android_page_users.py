"""The Android page is where the app's people are managed.

The operator asked for one screen that answers "which build is on the phones?"
and "who signs in from them?" — the account actions therefore live beside the
build, and they post to the same handlers the users page uses. Two copies of
that logic would drift: one door would accept a password the other refuses.
"""

import pytest

from stock_manager import lockout, mobile
from stock_manager.models import User

pytestmark = pytest.mark.django_db


def app_user(name="Warehouse Keeper", phone="01012345678", password="keeper-pass-1"):
    return mobile.create_app_user(phone=phone, password=password, name=name)


class TestTheList:
    def test_it_lists_the_people_who_sign_in_from_the_phone(self, client, manager):
        keeper = app_user()
        # Someone with no phone has no way into the app, so they are not listed.
        User.objects.create_user(username="webonly", password="test-pass-123")

        client.force_login(manager)
        response = client.get("/android/")

        assert response.status_code == 200
        names = [row.get_username() for row in response.context["app_users"]]
        assert keeper.get_username() in names
        assert "webonly" not in names

    def test_it_counts_the_active_ones(self, client, manager):
        app_user(phone="01012345678")
        closed = app_user(name="Closed One", phone="01099998888")
        closed.is_active = False
        closed.save(update_fields=["is_active"])

        client.force_login(manager)
        response = client.get("/android/")

        assert response.context["app_user_count"] == 2
        assert response.context["app_user_active"] == 1

    def test_a_locked_account_is_marked(self, client, manager):
        from axes.models import AccessAttempt

        keeper = app_user()
        # The lock is held by axes, so the row is written the way axes writes
        # it: the page must read the real state, not a flag of its own.
        AccessAttempt.objects.create(
            user_agent="pytest",
            username=keeper.get_username(),
            http_accept="",
            path_info="/accounts/login/",
            get_data="",
            post_data="",
            failures_since_start=lockout.failure_limit() or 3,
        )

        client.force_login(manager)
        response = client.get("/android/")

        row = next(r for r in response.context["app_users"] if r.pk == keeper.pk)
        assert row.lock["locked"] is True


class TestTheActions:
    def test_a_manager_creates_an_app_user_from_this_page(self, client, manager):
        client.force_login(manager)
        response = client.post(
            "/users/",
            {
                "action": "app-user",
                "name": "New Keeper",
                "phone": "01055556666",
                "password": "new-keeper-1",
                "next": "/android/",
            },
        )

        # Back where the form was, not on a different screen.
        assert response.status_code == 302
        assert response["Location"] == "/android/"
        created = User.objects.get(mobile_profile__phone__endswith="1055556666")
        assert created.mobile_profile.mobile_only is True

    def test_closing_an_account_returns_to_this_page(self, client, manager):
        keeper = app_user()
        client.force_login(manager)
        response = client.post(
            "/users/",
            {"action": "toggle-active", "user_id": keeper.pk, "next": "/android/"},
        )

        assert response.status_code == 302
        assert response["Location"] == "/android/"
        keeper.refresh_from_db()
        assert keeper.is_active is False

    def test_clearing_a_lockout_returns_to_this_page(self, client, manager):
        keeper = app_user()
        client.force_login(manager)
        response = client.post(
            "/users/",
            {"action": "unlock", "user_id": keeper.pk, "next": "/android/"},
        )

        assert response.status_code == 302
        assert response["Location"] == "/android/"

    def test_a_crafted_next_cannot_leave_the_site(self, client, manager):
        keeper = app_user()
        client.force_login(manager)
        response = client.post(
            "/users/",
            {
                "action": "toggle-active",
                "user_id": keeper.pk,
                "next": "//evil.example.com/steal",
            },
        )

        assert response.status_code == 302
        assert response["Location"] == "/users/"


class TestWhoMayDoIt:
    def test_a_shop_user_sees_the_people_but_no_actions(self, client, shop_user):
        app_user()
        client.force_login(shop_user)
        response = client.get("/android/")

        body = response.content.decode()
        assert 'id="appUsersTable"' in body
        # The form and the buttons are a manager's tools.
        assert 'id="addAppUserForm"' not in body
        assert "toggle-active" not in body
        assert 'id="publishReleaseForm"' not in body

    def test_the_page_promises_the_update_arrives_without_a_link(self, client, manager):
        client.force_login(manager)
        response = client.get("/android/")

        assert 'id="autoUpdateRule"' in response.content.decode()
