"""App accounts: who they are, which door they may use, and who controls them.

The rule under test is the one the operator asked for on /users/: a warehouse
worker can be given an account that lives in the phone and nowhere else — and
the web form must refuse it by name rather than admit it to pages it cannot use.
"""

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail

from stock_manager import mobile
from stock_manager.auth import is_app_only
from stock_manager.models import AuditEvent, MobileProfile

PASSWORD = "test-pass-123"
PHONE = "+201000000001"


@pytest.fixture
def app_user(groups, manager):
    return mobile.create_app_user(
        phone=PHONE,
        password=PASSWORD,
        name="Ahmed Mohamed",
        actor=manager,
    )


class TestTheAppAccount:
    def test_it_is_created_with_its_phone_and_its_group(self, app_user, groups):
        profile = MobileProfile.for_user(app_user)
        assert profile.phone == "201000000001"
        assert profile.mobile_only is True
        assert list(app_user.groups.values_list("name", flat=True)) == ["shop_users"]
        assert app_user.get_full_name() == "Ahmed Mohamed"

    def test_the_user_name_is_taken_from_the_phone_when_none_is_given(self, app_user):
        assert app_user.get_username() == "app-201000000001"

    def test_a_second_account_on_the_same_phone_is_refused(self, app_user, manager):
        with pytest.raises(mobile.MobileError) as exc:
            mobile.create_app_user(phone=PHONE, password=PASSWORD, actor=manager)
        assert exc.value.code == "phone_taken"

    def test_a_short_password_is_refused(self, manager):
        with pytest.raises(mobile.MobileError) as exc:
            mobile.create_app_user(phone="+201000000002", password="short", actor=manager)
        assert exc.value.code == "password_too_short"

    def test_an_unusable_phone_is_refused(self, manager):
        with pytest.raises(mobile.MobileError) as exc:
            mobile.create_app_user(phone="12", password=PASSWORD, actor=manager)
        assert exc.value.code == "phone_invalid"

    def test_the_creation_is_audited(self, app_user):
        assert AuditEvent.objects.filter(
            action=AuditEvent.USER_CREATED, entity_id=app_user.pk
        ).exists()


def _web_sign_in(client, username, password=PASSWORD):
    """The real web door. ``client.login()`` passes no request, and axes refuses
    to answer without one, so the form itself is what gets exercised."""
    response = client.post(
        "/accounts/login/", {"username": username, "password": password}
    )
    return response.status_code == 302 and response["Location"].rstrip("/") in ("", "/")


class TestWhichDoor:
    def test_the_web_refuses_an_app_only_account(self, app_user, client):
        assert _web_sign_in(client, app_user.get_username()) is False
        assert client.session.get("_auth_user_id") is None

    def test_the_app_admits_it(self, app_user, client):
        response = client.post(
            "/api/mobile/login/",
            data={"username": app_user.get_username(), "password": PASSWORD},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["user"]["mobileOnly"] is True

    def test_a_web_account_still_signs_in_on_the_web(self, shop_user, client):
        assert _web_sign_in(client, "shop1") is True
        assert is_app_only(shop_user) is False

    def test_an_account_can_be_given_the_web_back(self, app_user, manager, client):
        mobile.set_mobile_only(app_user, False, actor=manager)
        app_user.refresh_from_db()

        assert is_app_only(app_user) is False
        assert _web_sign_in(client, app_user.get_username()) is True

    def test_an_account_without_a_phone_cannot_be_made_app_only(self, shop_user, manager):
        with pytest.raises(mobile.MobileError) as exc:
            mobile.set_mobile_only(shop_user, True, actor=manager)
        assert exc.value.code == "no_phone"


class TestTheSignInRecord:
    def test_the_app_writes_the_last_sign_in_the_users_page_shows(self, app_user, client):
        assert app_user.last_login is None

        client.post(
            "/api/mobile/login/",
            data={"username": app_user.get_username(), "password": PASSWORD},
            content_type="application/json",
        )

        app_user.refresh_from_db()
        assert app_user.last_login is not None


class TestTheUsersPage:
    def _sign_in(self, client, manager):
        client.force_login(manager)

    def test_a_manager_creates_an_app_account_in_one_step(self, client, manager):
        self._sign_in(client, manager)

        response = client.post(
            "/users/",
            data={
                "action": "app-user",
                "name": "Sara Ali",
                "phone": "+201000000009",
                "password": PASSWORD,
            },
        )

        assert response.status_code == 302
        user = User.objects.get(first_name="Sara")
        profile = MobileProfile.for_user(user)
        assert profile.phone == "201000000009"
        assert profile.mobile_only is True

    def test_a_bad_phone_is_reported_and_nothing_is_created(self, client, manager):
        self._sign_in(client, manager)
        before = User.objects.count()

        response = client.post(
            "/users/",
            data={"action": "app-user", "phone": "12", "password": PASSWORD},
            follow=True,
        )

        assert User.objects.count() == before
        assert "رقم الهاتف غير صحيح" in response.content.decode()

    def test_a_manager_closes_and_reopens_an_account(self, client, manager, app_user):
        self._sign_in(client, manager)

        client.post("/users/", data={"action": "toggle-active", "user_id": app_user.pk})
        app_user.refresh_from_db()
        assert app_user.is_active is False

        client.post("/users/", data={"action": "toggle-active", "user_id": app_user.pk})
        app_user.refresh_from_db()
        assert app_user.is_active is True

    def test_the_last_manager_cannot_be_closed(self, client, manager, shop_user):
        """No shell on the deployed host: closing the last manager locks the page."""
        self._sign_in(client, manager)
        manager.first_name = "المدير"
        manager.save()
        # a second manager so the fixture's manager is not the only one
        other = User.objects.create_user(username="boss", password=PASSWORD)
        other.groups.add(Group.objects.get(name="managers"))

        client.post("/users/", data={"action": "toggle-active", "user_id": other.pk})
        other.refresh_from_db()
        assert other.is_active is False

        # now `manager` is the last one, and `boss` is closed
        client.post("/users/", data={"action": "toggle-active", "user_id": manager.pk})
        manager.refresh_from_db()
        assert manager.is_active is True

    def test_a_nonsense_user_id_is_not_a_crash(self, client, manager):
        self._sign_in(client, manager)

        response = client.post(
            "/users/", data={"action": "toggle-active", "user_id": "abc"}, follow=True
        )

        assert response.status_code == 200
        said = [str(message) for message in response.context["messages"]]
        assert said == ["That user does not exist."]

    def test_a_manager_cannot_close_their_own_account(self, client, manager):
        self._sign_in(client, manager)

        client.post("/users/", data={"action": "toggle-active", "user_id": manager.pk})

        manager.refresh_from_db()
        assert manager.is_active is True

    def test_the_table_says_which_door_each_account_uses(
        self, client, manager, app_user, shop_user
    ):
        self._sign_in(client, manager)

        page = client.get("/users/").content.decode()

        assert "تطبيق فقط" in page or "App only" in page
        assert "ويب فقط" in page or "Web only" in page

    def test_the_edit_panel_switches_the_door(self, client, manager, app_user):
        self._sign_in(client, manager)

        client.post(
            "/users/",
            data={
                "action": "update",
                "user_id": app_user.pk,
                "first_name": "Ahmed",
                "last_name": "Mohamed",
                "is_active": "on",
                "has_phone": "1",
                # mobile_only unchecked: the web door is given back
            },
        )

        app_user.refresh_from_db()
        assert MobileProfile.for_user(app_user).mobile_only is False
