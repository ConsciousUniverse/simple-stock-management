"""The users screen: creating accounts, changing their role, and shutting them.

Everything here is a manager's job, so the gate matters as much as the form: a
shop user must never reach the page that hands out roles.
"""

import pytest
from django.contrib.auth.models import User

from stock_manager.models import AuditEvent

pytestmark = pytest.mark.django_db


def post(client, **fields):
    data = {"action": "create"}
    data.update(fields)
    return client.post("/users/", data, follow=True)


class TestAccess:
    def test_a_manager_opens_the_page(self, client, manager):
        client.force_login(manager)
        response = client.get("/users/")
        assert response.status_code == 200
        assert b"usersTable" in response.content

    def test_a_shop_user_is_sent_away(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/users/")
        assert response.status_code == 302
        assert response.headers["Location"] == "/"

    def test_an_anonymous_visitor_is_sent_to_the_sign_in(self, client):
        response = client.get("/users/")
        assert response.status_code == 302
        assert "/accounts/login/" in response.headers["Location"]


class TestCreating:
    def test_a_new_account_is_created_with_its_role_and_a_hashed_password(
        self, client, manager, groups
    ):
        client.force_login(manager)

        response = post(
            client,
            username="new.tech",
            password="a-strong-pass-1",
            email="tech@example.com",
            first_name="New",
            last_name="Tech",
            groups=["shop_users"],
        )

        assert response.status_code == 200
        user = User.objects.get(username="new.tech")
        assert user.groups.filter(name="shop_users").exists()
        assert user.check_password("a-strong-pass-1")
        # The password is stored hashed, never in the clear.
        assert "a-strong-pass-1" not in user.password
        assert AuditEvent.objects.filter(action=AuditEvent.USER_CREATED).exists()

    def test_a_duplicate_user_name_is_refused(self, client, manager):
        client.force_login(manager)
        before = User.objects.count()

        response = post(client, username="manager", password="a-strong-pass-1")

        assert User.objects.count() == before
        assert "That user name is already taken." in response.content.decode()

    def test_a_short_password_is_refused(self, client, manager):
        client.force_login(manager)

        response = post(client, username="shorty", password="123")

        assert not User.objects.filter(username="shorty").exists()
        assert "8" in response.content.decode()

    def test_an_empty_user_name_is_refused(self, client, manager):
        client.force_login(manager)
        before = User.objects.count()

        post(client, username="", password="a-strong-pass-1")

        assert User.objects.count() == before

    def test_a_shop_user_cannot_create_an_account(self, client, shop_user):
        client.force_login(shop_user)
        before = User.objects.count()

        post(client, username="sneaky", password="a-strong-pass-1", groups=["managers"])

        assert User.objects.count() == before


class TestTheRoleIsReadable:
    def test_the_groups_are_named_in_the_readers_words(self, client, manager, groups):
        client.force_login(manager)

        response = client.get("/users/")

        labels = [option["label"] for option in response.context["groups"]]
        assert "Warehouse manager" in labels
        assert "Site user" in labels
        assert "managers" not in labels

    def test_the_labels_follow_the_chosen_language(self, client, manager):
        client.force_login(manager)
        client.cookies["django_language"] = "ar"

        response = client.get("/users/")

        labels = [str(option["label"]) for option in response.context["groups"]]
        assert "مدير المخزن" in labels


class TestEditing:
    def test_the_edit_form_opens_on_the_chosen_account(self, client, manager, shop_user):
        client.force_login(manager)

        response = client.get(f"/users/?edit={shop_user.pk}")

        assert response.status_code == 200
        assert response.context["editing"] == shop_user
        assert b"editUserForm" in response.content

    def test_the_role_is_replaced_and_the_change_is_recorded(
        self, client, manager, shop_user, groups
    ):
        client.force_login(manager)

        client.post(
            "/users/",
            {
                "action": "update",
                "user_id": shop_user.pk,
                "first_name": "Site",
                "last_name": "One",
                "email": "site1@example.com",
                "is_active": "on",
                "groups": ["managers"],
            },
        )

        shop_user.refresh_from_db()
        assert [group.name for group in shop_user.groups.all()] == ["managers"]
        assert AuditEvent.objects.filter(action=AuditEvent.USER_UPDATED).exists()

    def test_deactivating_an_account_is_recorded_as_a_deactivation(
        self, client, manager, shop_user
    ):
        client.force_login(manager)

        client.post(
            "/users/",
            {
                "action": "update",
                "user_id": shop_user.pk,
                "email": "site1@example.com",
            },
        )

        shop_user.refresh_from_db()
        assert shop_user.is_active is False
        assert AuditEvent.objects.filter(action=AuditEvent.USER_DEACTIVATED).exists()

    def test_a_manager_can_reset_a_password_and_it_works(
        self, client, manager, shop_user
    ):
        client.force_login(manager)

        client.post(
            "/users/",
            {"action": "password", "user_id": shop_user.pk, "password": "brand-new-pass-9"},
        )

        shop_user.refresh_from_db()
        assert shop_user.check_password("brand-new-pass-9")
        assert AuditEvent.objects.filter(action=AuditEvent.PASSWORD_CHANGED).exists()

    def test_an_unknown_account_is_reported_not_crashed(self, client, manager):
        client.force_login(manager)

        response = client.post(
            "/users/", {"action": "update", "user_id": 999999}, follow=True
        )

        assert response.status_code == 200
        assert "That user does not exist." in response.content.decode()
