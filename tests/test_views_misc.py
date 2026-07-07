import pytest

from stock_manager.models import Admin

pytestmark = pytest.mark.django_db


class TestIndexView:
    def test_anonymous_redirected_to_login(self, client):
        response = client.get("/")
        assert response.status_code == 302
        assert response.url == "/accounts/login/?next=/"

    def test_authenticated_user_gets_index_page(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/")
        assert response.status_code == 200
        assert "index.html" in [t.name for t in response.templates]

    def test_csrf_cookie_is_set(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/")
        assert "csrftoken" in response.cookies


class TestGetUser:
    def test_anonymous_denied(self, api_client):
        assert api_client.get("/auth/user/").status_code == 403

    def test_returns_identity_and_groups(self, shop_client, shop_user):
        response = shop_client.get("/auth/user/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == shop_user.id
        assert data["username"] == "shop1"
        assert data["email"] == "shop1@example.com"
        assert data["groups"] == ["shop_users"]


class TestEditLockEndpoints:
    def test_set_requires_authentication(self, api_client):
        response = api_client.post(
            "/api/set_edit_lock_status/", {"edit_lock_status": True}, format="json"
        )
        assert response.status_code == 403

    def test_set_requires_manager(self, shop_client, app_config):
        response = shop_client.post(
            "/api/set_edit_lock_status/", {"edit_lock_status": True}, format="json"
        )
        assert response.status_code == 403

    def test_manager_can_toggle(self, manager_client, app_config):
        response = manager_client.post(
            "/api/set_edit_lock_status/", {"edit_lock_status": True}, format="json"
        )
        assert response.status_code == 200
        assert response.json() == {"edit_lock": True}
        assert Admin.is_edit_locked() is True

        response = manager_client.post(
            "/api/set_edit_lock_status/", {"edit_lock_status": False}, format="json"
        )
        assert response.json() == {"edit_lock": False}
        assert Admin.is_edit_locked() is False

    def test_set_creates_config_row_when_missing(self, manager_client, db):
        assert Admin.objects.count() == 0
        manager_client.post(
            "/api/set_edit_lock_status/", {"edit_lock_status": True}, format="json"
        )
        assert Admin.objects.filter(id=1).exists()

    def test_get_requires_authentication(self, api_client, app_config):
        assert api_client.get("/api/get_edit_lock_status/").status_code == 403

    def test_get_returns_current_status(self, shop_client, app_config):
        response = shop_client.get("/api/get_edit_lock_status/")
        assert response.status_code == 200
        assert response.json() == {"edit_lock": False}

        app_config.edit_lock = True
        app_config.save()
        response = shop_client.get("/api/get_edit_lock_status/")
        assert response.json() == {"edit_lock": True}

    def test_get_defaults_to_unlocked_without_config_row(self, shop_client):
        # A fresh install has no Admin row yet; the endpoint must not crash.
        response = shop_client.get("/api/get_edit_lock_status/")
        assert response.status_code == 200
        assert response.json() == {"edit_lock": False}

    def test_get_rejects_other_methods(self, shop_client, app_config):
        assert shop_client.post("/api/get_edit_lock_status/").status_code == 405


class TestAppConfigEndpoint:
    def test_anonymous_denied(self, api_client):
        assert api_client.get("/api/app_config/").status_code == 403

    def test_returns_configured_values(self, shop_client, app_config):
        app_config.records_per_page = 50
        app_config.allow_upload_deletions = True
        app_config.save()

        response = shop_client.get("/api/app_config/")

        assert response.status_code == 200
        assert response.json() == {
            "records_per_page": 50,
            "allow_upload_deletions": True,
        }

    def test_returns_defaults_without_config_row(self, shop_client):
        response = shop_client.get("/api/app_config/")
        assert response.status_code == 200
        assert response.json() == {
            "records_per_page": 25,
            "allow_upload_deletions": False,
        }


class TestDeadTokenEndpointRemoved:
    """
    The token-auth endpoint was unused: DRF token authentication is not
    configured (no TokenAuthentication class, and rest_framework.authtoken is
    not installed), so it could only ever error. It is removed to shrink the
    attack surface.
    """

    def test_token_endpoint_returns_404(self, client):
        assert client.post("/auth/token/", {}).status_code == 404
        assert client.post("/api/auth/token/", {}).status_code == 404
