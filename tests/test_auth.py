import importlib

import pytest
from django.urls import clear_url_caches

import ssm.urls

pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"


class TestLoginLogout:
    def test_login_page_renders(self, client):
        response = client.get(LOGIN_URL)
        assert response.status_code == 200
        assert "registration/login.html" in [t.name for t in response.templates]

    def test_valid_credentials_redirect_to_index(self, client, shop_user):
        response = client.post(
            LOGIN_URL, {"username": "shop1", "password": "test-pass-123"}
        )
        assert response.status_code == 302
        assert response.url == "/"

    def test_invalid_credentials_rerender_login_page(self, client, shop_user):
        response = client.post(
            LOGIN_URL, {"username": "shop1", "password": "wrong-password"}
        )
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_logout_redirects_to_login(self, client, shop_user):
        client.force_login(shop_user)
        response = client.post("/accounts/logout/")
        assert response.status_code == 302
        assert response.url == LOGIN_URL


class TestBruteForceLockout:
    """django-axes: AXES_FAILURE_LIMIT is pinned to 3 in test settings."""

    @pytest.fixture(autouse=True)
    def axes_enabled(self, settings):
        settings.AXES_ENABLED = True

    def fail_login(self, client, username="shop1"):
        return client.post(
            LOGIN_URL, {"username": username, "password": "wrong-password"}
        )

    def test_locked_out_after_failure_limit(self, client, shop_user):
        for _ in range(3):
            self.fail_login(client)
        # Even the correct password is now rejected with a lockout response.
        response = client.post(
            LOGIN_URL, {"username": "shop1", "password": "test-pass-123"}
        )
        assert response.status_code == 429

    def test_lockout_is_per_username(self, client, shop_user, other_shop_user):
        """
        One user's failures must never lock out other users. (IP-based
        lockout cannot apply here because AXES_CLIENT_IP_CALLABLE nulls the
        client IP for privacy, which would make it a global lockout.)
        """
        for _ in range(3):
            self.fail_login(client, username="shop1")
        response = client.post(
            LOGIN_URL, {"username": "shop2", "password": "test-pass-123"}
        )
        assert response.status_code == 302

    def test_failures_below_limit_do_not_lock_out(self, client, shop_user):
        for _ in range(2):
            self.fail_login(client)
        response = client.post(
            LOGIN_URL, {"username": "shop1", "password": "test-pass-123"}
        )
        assert response.status_code == 302


class TestPasswordChangeToggle:
    """
    ssm.urls conditionally mounts redirect views for the password-change
    pages depending on settings.ALLOW_PW_CHANGE, evaluated at import time —
    so the urlconf has to be reloaded to exercise each branch.
    """

    @staticmethod
    def reload_urlconf():
        importlib.reload(ssm.urls)
        clear_url_caches()

    def test_password_change_available_by_default(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/accounts/password_change/")
        assert response.status_code == 200

    def test_password_change_redirected_when_disabled(
        self, client, shop_user, settings
    ):
        client.force_login(shop_user)
        settings.ALLOW_PW_CHANGE = False
        try:
            self.reload_urlconf()
            response = client.get("/accounts/password_change/")
            assert response.status_code == 302
            assert response.url == "/"

            response = client.get("/admin/password_change/")
            assert response.status_code == 302
            assert response.url == "/admin/"
        finally:
            settings.ALLOW_PW_CHANGE = True
            self.reload_urlconf()
