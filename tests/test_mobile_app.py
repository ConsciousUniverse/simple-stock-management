"""The phone is the identity in the app, and the app cannot change it.

Two things are being pinned here, and both are security properties rather than
conveniences:

* **One person, one number.** ``+20 101 234 5678``, ``00201012345678`` and
  ``01012345678`` must resolve to the same account, or a typo becomes a second
  identity nobody verified.
* **Only a manager moves a number.** The app can ASK; the refusal must be an
  explicit answer, not a silently ignored field the client believes it set.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from stock_manager import mobile
from stock_manager.models import (
    AppRelease,
    AuditEvent,
    MobileProfile,
    PhoneChangeRequest,
)
from stock_manager.phones import canonical_phone, is_valid_phone

pytestmark = pytest.mark.django_db

PASSWORD = "test-pass-123"


def post_json(client, path, payload, token=None):
    extra = {}
    if token:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    return client.post(
        path, data=json.dumps(payload), content_type="application/json", **extra
    )


def sign_in(client, phone="01012345678", password=PASSWORD):
    return post_json(
        client, "/api/mobile/login/", {"phone": phone, "password": password}
    )


@pytest.fixture
def phone_user(shop_user):
    mobile.set_phone(shop_user, "01012345678")
    return shop_user


@pytest.fixture
def token(client, phone_user):
    response = sign_in(client)
    assert response.status_code == 200, response.content
    return response.json()["token"]


class TestOnePersonOneNumber:
    @pytest.mark.parametrize(
        "written",
        [
            "+20 101 234 5678",
            "00201012345678",
            "01012345678",
            "0101-234-5678",
            "  01012345678  ",
            "\u2066+201012345678\u2069",  # an invisible bidi mark from a copy-paste
        ],
    )
    def test_every_spelling_is_one_number(self, written):
        assert canonical_phone(written) == "201012345678"

    @pytest.mark.parametrize("written", ["", "123", "not a phone", "12"])
    def test_a_number_too_short_is_not_a_phone(self, written):
        assert is_valid_phone(written) is False

    def test_a_number_saved_one_way_signs_in_another(self, client, phone_user):
        assert sign_in(client, "+20 101 234 5678").status_code == 200


class TestSigningIn:
    def test_the_phone_and_password_sign_in(self, client, phone_user):
        response = sign_in(client)

        assert response.status_code == 200
        body = response.json()
        assert body["token"]
        assert body["user"]["phone"] == "+201012345678"
        assert body["user"]["phoneLocked"] is True

    def test_the_token_opens_the_profile(self, client, token):
        response = client.get(
            "/api/mobile/me/", HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        assert response.status_code == 200
        assert response.json()["username"] == "shop1"

    def test_an_unknown_phone_is_told_so(self, client, phone_user):
        response = sign_in(client, "01000000000")

        assert response.status_code == 401
        assert response.json()["code"] == "phone_unknown"

    def test_a_wrong_password_is_refused(self, client, phone_user):
        response = sign_in(client, password="wrong")

        assert response.status_code == 401
        assert response.json()["code"] == "bad_password"

    def test_a_disabled_account_is_refused(self, client, phone_user):
        phone_user.is_active = False
        phone_user.save(update_fields=["is_active"])

        response = sign_in(client)

        assert response.status_code == 403
        assert response.json()["code"] == "account_disabled"

    def test_a_session_can_be_revoked(self, client, token):
        assert (
            client.post(
                "/api/mobile/logout/", HTTP_AUTHORIZATION=f"Bearer {token}"
            ).status_code
            == 200
        )

        assert (
            client.get("/api/mobile/me/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code
            == 401
        )

    def test_an_absent_token_is_refused(self, client):
        assert client.get("/api/mobile/me/").status_code == 401

    def test_signing_in_is_recorded(self, client, phone_user):
        sign_in(client)

        assert AuditEvent.objects.filter(action=AuditEvent.LOGIN).exists()


class TestSigningInWithAUserName:
    """The web uses a user name; the app must not force a second identity.

    A phone is what the manager sets and what the app displays, but a person
    who knows their user name should not be locked out of the phone app.
    """

    def test_the_user_name_and_password_sign_in(self, client, phone_user):
        response = post_json(
            client, "/api/mobile/login/", {"username": "shop1", "password": PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["user"]["phone"] == "+201012345678"

    def test_the_user_name_is_case_insensitive(self, client, phone_user):
        response = post_json(
            client, "/api/mobile/login/", {"username": "SHOP1", "password": PASSWORD}
        )

        assert response.status_code == 200

    def test_a_user_name_with_the_wrong_password_is_refused(self, client, phone_user):
        response = post_json(
            client, "/api/mobile/login/", {"username": "shop1", "password": "nope"}
        )

        assert response.status_code == 401
        assert response.json()["code"] == "bad_password"

    def test_an_unknown_user_name_is_told_so(self, client, phone_user):
        response = post_json(
            client, "/api/mobile/login/", {"username": "ghost", "password": PASSWORD}
        )

        assert response.status_code == 401
        assert response.json()["code"] == "phone_unknown"

    def test_a_user_without_a_phone_still_signs_in_and_sees_no_number(
        self, client, shop_user
    ):
        # No MobileProfile row: the account exists, the number was never set.
        response = post_json(
            client, "/api/mobile/login/", {"username": "shop1", "password": PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["user"]["phone"] == ""

    def test_the_number_wins_when_it_belongs_to_someone(self, client, phone_user, other_shop_user):
        # other_shop_user has the user name "shop2"; give them a number and
        # check a sign-in by that number lands on THEM, not on shop1.
        mobile.set_phone(other_shop_user, "01055555555")

        response = sign_in(client, "01055555555")

        assert response.status_code == 200
        assert response.json()["user"]["username"] == "shop2"


class TestTheAppCannotMoveThePhone:
    def test_writing_the_phone_directly_is_refused(self, client, token, phone_user):
        response = post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"phone": "01099999999"},
            token=token,
        )

        assert response.status_code == 403
        assert response.json()["code"] == "phone_locked"
        assert MobileProfile.for_user(phone_user).phone == "201012345678"

    def test_asking_for_a_new_number_changes_nothing(self, client, token, phone_user):
        response = post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999", "reason": "شريحة جديدة"},
            token=token,
        )

        assert response.status_code == 201
        assert MobileProfile.for_user(phone_user).phone == "201012345678"
        record = PhoneChangeRequest.objects.get(user=phone_user)
        assert record.status == PhoneChangeRequest.PENDING
        assert record.requested_phone == "201099999999"

    def test_asking_again_replaces_the_pending_request(self, client, token, phone_user):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999"},
            token=token,
        )
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01088888888"},
            token=token,
        )

        records = PhoneChangeRequest.objects.filter(user=phone_user)
        assert records.count() == 1
        assert records.first().requested_phone == "201088888888"

    def test_a_number_belonging_to_someone_else_is_refused(
        self, client, token, phone_user, other_shop_user
    ):
        mobile.set_phone(other_shop_user, "01077777777")

        response = post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01077777777"},
            token=token,
        )

        assert response.status_code == 409
        assert response.json()["code"] == "phone_taken"

    def test_the_profile_shows_the_pending_request(self, client, token):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999"},
            token=token,
        )

        body = client.get(
            "/api/mobile/me/", HTTP_AUTHORIZATION=f"Bearer {token}"
        ).json()

        assert body["pendingPhoneChange"]["requestedPhone"] == "+201099999999"


class TestAManagerDecides:
    def test_approval_moves_the_number_and_is_recorded(
        self, client, manager, phone_user, token
    ):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999"},
            token=token,
        )
        record = PhoneChangeRequest.objects.get(user=phone_user)

        mobile.decide_phone_change(record, manager, approve=True, note="تم التحقق")

        record.refresh_from_db()
        assert record.status == PhoneChangeRequest.APPROVED
        assert record.decided_by == manager
        assert MobileProfile.for_user(phone_user).phone == "201099999999"
        assert AuditEvent.objects.filter(action=AuditEvent.PHONE_CHANGED).exists()
        assert AuditEvent.objects.filter(
            action=AuditEvent.PHONE_REQUEST_DECIDED
        ).exists()

    def test_the_new_number_signs_in_and_the_old_one_does_not(
        self, client, manager, phone_user, token
    ):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999"},
            token=token,
        )
        mobile.decide_phone_change(
            PhoneChangeRequest.objects.get(user=phone_user), manager, approve=True
        )

        assert sign_in(client, "01099999999").status_code == 200
        assert sign_in(client, "01012345678").status_code == 401

    def test_refusing_leaves_the_number_alone(self, client, manager, phone_user, token):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999"},
            token=token,
        )
        record = PhoneChangeRequest.objects.get(user=phone_user)

        mobile.decide_phone_change(record, manager, approve=False, note="غير معروف")

        record.refresh_from_db()
        assert record.status == PhoneChangeRequest.REJECTED
        assert MobileProfile.for_user(phone_user).phone == "201012345678"

    def test_a_decided_request_cannot_be_decided_again(self, manager, phone_user):
        record = PhoneChangeRequest.objects.create(
            user=phone_user, requested_phone="201099999999"
        )
        mobile.decide_phone_change(record, manager, approve=True)

        with pytest.raises(mobile.MobileError) as refusal:
            mobile.decide_phone_change(record, manager, approve=True)

        assert refusal.value.status == 409

    def test_a_manager_sets_a_number_from_the_users_page(self, client, manager, shop_user):
        client.force_login(manager)

        response = client.post(
            "/users/",
            {"action": "phone", "user_id": shop_user.pk, "phone": "+20 100 555 6666"},
            follow=True,
        )

        assert response.status_code == 200
        assert MobileProfile.for_user(shop_user).phone == "201005556666"

    def test_a_shop_user_cannot_set_a_number(self, client, shop_user, other_shop_user):
        client.force_login(shop_user)

        client.post(
            "/users/",
            {"action": "phone", "user_id": other_shop_user.pk, "phone": "01011111111"},
            follow=True,
        )

        assert MobileProfile.for_user(other_shop_user) is None

    def test_two_people_cannot_share_a_number(self, client, manager, shop_user, other_shop_user):
        mobile.set_phone(shop_user, "01012345678")
        client.force_login(manager)

        response = client.post(
            "/users/",
            {"action": "phone", "user_id": other_shop_user.pk, "phone": "01012345678"},
            follow=True,
        )

        assert MobileProfile.for_user(other_shop_user) is None
        assert "مسجَّل" in response.content.decode()

    def test_the_page_lists_the_pending_requests(self, client, manager, phone_user, token):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999", "reason": "شريحة جديدة"},
            token=token,
        )
        client.force_login(manager)

        response = client.get("/users/")

        assert b"phoneRequests" in response.content
        assert b"201099999999" in response.content

        # The phone form lives in the edit panel, and it opens on the number
        # the account already has.
        panel = client.get(f"/users/?edit={phone_user.pk}")
        assert b"phoneForm" in panel.content
        assert b"+201012345678" in panel.content

    def test_a_manager_approves_from_the_page(self, client, manager, phone_user, token):
        post_json(
            client,
            "/api/mobile/phone-change-requests/",
            {"requestedPhone": "01099999999"},
            token=token,
        )
        record = PhoneChangeRequest.objects.get(user=phone_user)
        client.force_login(manager)

        client.post(
            "/users/",
            {"action": "phone-request", "request_id": record.pk, "decision": "approve"},
            follow=True,
        )

        record.refresh_from_db()
        assert record.status == PhoneChangeRequest.APPROVED
        assert MobileProfile.for_user(phone_user).phone == "201099999999"


class TestTheAppIsToldAboutANewBuild:
    def test_it_answers_without_signing_in(self, client):
        assert client.get("/api/mobile/version/").status_code == 200

    def test_nothing_published_offers_no_update(self, client):
        body = client.get("/api/mobile/version/?code=5").json()

        assert body["updateAvailable"] is False
        assert body["latest"] is None

    def test_a_higher_build_is_an_update(self, client):
        AppRelease.objects.create(
            version="1.1.0",
            version_code=11,
            download_url="https://example.com/v11.apk",
            notes="Faster scan",
        )

        body = client.get("/api/mobile/version/?code=10").json()

        assert body["updateAvailable"] is True
        assert body["latest"]["versionCode"] == 11
        assert body["latest"]["downloadUrl"] == "https://example.com/v11.apk"

    def test_the_same_build_is_not_an_update(self, client):
        AppRelease.objects.create(
            version="1.1.0", version_code=11, download_url="https://example.com/v11.apk"
        )

        body = client.get("/api/mobile/version/?code=11").json()

        assert body["updateAvailable"] is False
        assert body["latest"]["current"] is True

    def test_a_phone_ahead_of_the_server_is_not_offered_a_downgrade(self, client):
        AppRelease.objects.create(
            version="1.1.0", version_code=11, download_url="https://example.com/v11.apk"
        )

        body = client.get("/api/mobile/version/?code=12").json()

        assert body["updateAvailable"] is False

    def test_a_mandatory_build_says_so(self, client):
        AppRelease.objects.create(
            version="1.2.0",
            version_code=12,
            download_url="https://example.com/v12.apk",
            mandatory=True,
        )

        body = client.get("/api/mobile/version/?code=11").json()

        assert body["latest"]["mandatory"] is True

    def test_the_answer_is_not_cached_by_a_proxy(self, client):
        response = client.get("/api/mobile/version/")

        assert response["Cache-Control"] == "no-store"

    def test_a_phone_that_does_not_say_its_build_is_told_the_latest(self, client):
        AppRelease.objects.create(
            version="1.3.0", version_code=13, download_url="https://example.com/v13.apk"
        )

        body = client.get("/api/mobile/version/").json()

        assert body["latest"]["versionCode"] == 13
        assert body["updateAvailable"] is False


class TestWhichBuildIsNewest:
    def test_the_highest_build_number_wins_over_the_newest_row(self):
        AppRelease.objects.create(
            version="1.0.0", version_code=10, download_url="https://example.com/10.apk"
        )
        AppRelease.objects.create(
            version="0.9.0", version_code=9, download_url="https://example.com/9.apk"
        )

        assert AppRelease.latest().version_code == 10

    def test_a_release_published_before_numbers_existed_still_shows(self):
        AppRelease.objects.create(
            version="0.1.0", download_url="https://example.com/old.apk"
        )

        assert AppRelease.latest().version == "0.1.0"


class TestTheLoginAttemptLimit:
    def test_repeated_failures_stop_being_answered(self, client, phone_user):
        for _ in range(mobile_api_limit()):
            sign_in(client, password="wrong")

        response = sign_in(client, password="wrong")

        assert response.status_code == 429
        assert response.json()["code"] == "too_many_attempts"


def mobile_api_limit():
    from stock_manager.mobile_api import LOGIN_ATTEMPT_LIMIT

    return LOGIN_ATTEMPT_LIMIT
