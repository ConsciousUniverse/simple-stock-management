"""One account, one phone.

An account signed in on two phones is two people moving stock in one name, and
the audit trail cannot tell them apart. These tests pin the rule from both ends:
the second phone is refused with a sentence that says which phone has it, and a
manager's «مسح الجهاز» frees the account and stops the old phone's token.
"""

import json

import pytest
from django.core.cache import cache
from django.test import Client

from stock_manager import mobile
from stock_manager.models import MobileSession

pytestmark = pytest.mark.django_db

PASSWORD = "test-pass-123"
PHONE = "01012345678"


def login(client, password=PASSWORD, device_id="", device="Pixel 7"):
    return client.post(
        "/api/mobile/login/",
        data=json.dumps(
            {"phone": PHONE, "password": password, "device": device, "deviceId": device_id}
        ),
        content_type="application/json",
    )


@pytest.fixture
def app_user(shop_user):
    mobile.set_phone(shop_user, PHONE)
    cache.clear()
    return shop_user


def test_the_first_phone_claims_the_account(app_user):
    response = login(Client(), device_id="phone-a", device="Samsung A12")

    assert response.status_code == 200, response.content
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == "phone-a"
    assert app_user.mobile_profile.device_label == "Samsung A12"
    assert app_user.mobile_profile.device_bound_at is not None


def test_the_same_phone_signs_in_again(app_user):
    assert login(Client(), device_id="phone-a").status_code == 200
    assert login(Client(), device_id="phone-a").status_code == 200


def test_a_second_phone_is_refused_by_name(app_user):
    assert login(Client(), device_id="phone-a", device="Samsung A12").status_code == 200

    response = login(Client(), device_id="phone-b", device="Xiaomi Redmi")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "device_locked"
    # The sentence must name the phone that has the account, or the person has
    # nothing to tell the manager.
    assert "Samsung A12" in body["error"]
    assert "مستخدمو التطبيق" in body["error"]
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == "phone-a"


def test_clearing_the_device_frees_the_account_and_kills_the_old_token(app_user):
    first = login(Client(), device_id="phone-a", device="Samsung A12")
    assert first.status_code == 200
    token = first.json()["token"]

    # The old phone is still signed in until a manager clears it.
    me = Client().get("/api/mobile/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert me.status_code == 200

    mobile.clear_device(app_user, by=app_user)

    # The token it holds stops working at once, not when it expires.
    after = Client().get("/api/mobile/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert after.status_code == 401

    second = login(Client(), device_id="phone-b", device="Xiaomi Redmi")
    assert second.status_code == 200, second.content
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == "phone-b"


def test_clearing_revokes_the_sessions_it_does_not_delete_the_rows(app_user):
    login(Client(), device_id="phone-a")
    mobile.clear_device(app_user, by=app_user)

    assert MobileSession.objects.filter(user=app_user, revoked_at__isnull=True).count() == 0
    assert MobileSession.objects.filter(user=app_user).exists()


def test_a_phone_that_sends_no_id_is_not_locked_out(app_user):
    """The build already in people's hands does not send a device id."""
    assert login(Client(), device_id="").status_code == 200
    assert login(Client(), device_id="").status_code == 200
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == ""


def test_a_wrong_password_does_not_bind_the_phone(app_user):
    response = login(Client(), password="wrong-password", device_id="phone-a")

    assert response.status_code == 401
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == ""


def test_a_manager_clears_the_device_from_the_users_page(app_user, manager):
    login(Client(), device_id="phone-a", device="Samsung A12")
    client = Client()
    client.force_login(manager)

    response = client.post(
        "/users/",
        {"action": "clear-device", "user_id": str(app_user.pk), "next": "/android/"},
        follow=True,
    )

    assert response.status_code == 200
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == ""
    assert login(Client(), device_id="phone-b").status_code == 200


def test_clearing_is_manager_only(app_user, shop_user):
    login(Client(), device_id="phone-a")
    client = Client()
    client.force_login(shop_user)

    response = client.post(
        "/users/",
        {"action": "clear-device", "user_id": str(app_user.pk), "next": "/android/"},
        follow=True,
    )

    assert response.status_code in {200, 302, 403}
    app_user.mobile_profile.refresh_from_db()
    assert app_user.mobile_profile.device_id == "phone-a"

def test_the_users_page_shows_which_phone_holds_the_account(app_user, manager):
    login(Client(), device_id="phone-a", device="Samsung A12")
    client = Client()
    client.force_login(manager)

    body = client.get("/android/").content.decode()

    # The manager has to see WHICH phone before deciding to free the account.
    assert "Samsung A12" in body
    assert "Phone bound to" in body
    assert "clear-device" in body
