"""
Deployment wiring (Render).

These tests pin the pieces a platform deploy depends on: an unauthenticated
liveness probe, WhiteNoise serving ``/static/`` from the WSGI app, the managed
Postgres URL being honoured, and the pinned dependency list that the build
installs. Without them a deploy fails at boot rather than in CI.
"""

import importlib
import json
from pathlib import Path

import pytest

import ssm.settings as base_settings

BASE_DIR = Path(base_settings.BASE_DIR)


@pytest.mark.django_db
class TestHealthEndpoint:
    def test_is_public_and_returns_ok(self, client):
        response = client.get("/healthz")

        assert response.status_code == 200
        assert json.loads(response.content) == {"status": "ok"}

    def test_does_not_redirect_to_the_login_page(self, client):
        response = client.get("/healthz")

        assert response.status_code == 200
        assert "Location" not in response


class TestSettingsWiring:
    def test_whitenoise_serves_static_files(self):
        assert "whitenoise.middleware.WhiteNoiseMiddleware" in base_settings.MIDDLEWARE
        # ... immediately after SecurityMiddleware, as WhiteNoise documents.
        assert (
            base_settings.MIDDLEWARE.index(
                "whitenoise.middleware.WhiteNoiseMiddleware"
            )
            == base_settings.MIDDLEWARE.index(
                "django.middleware.security.SecurityMiddleware"
            )
            + 1
        )
        assert (
            base_settings.STORAGES["staticfiles"]["BACKEND"]
            == "whitenoise.storage.CompressedStaticFilesStorage"
        )

    def test_render_hostname_is_allowed(self, monkeypatch):
        monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "example.com")
        monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "ssm-demo.onrender.com")
        try:
            module = importlib.reload(base_settings)
            assert "example.com" in module.ALLOWED_HOSTS
            assert "ssm-demo.onrender.com" in module.ALLOWED_HOSTS
        finally:
            monkeypatch.undo()
            importlib.reload(base_settings)

    def test_database_url_selects_postgres(self, monkeypatch):
        monkeypatch.setenv(
            "DATABASE_URL", "postgres://user:pass@db.example.com:5432/ssm"
        )
        try:
            module = importlib.reload(base_settings)
            config = module.DATABASES["default"]
            assert config["ENGINE"] == "django.db.backends.postgresql"
            assert config["NAME"] == "ssm"
            assert config["HOST"] == "db.example.com"
        finally:
            monkeypatch.undo()
            importlib.reload(base_settings)

    def test_sqlite_remains_the_local_default(self):
        assert base_settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")


class TestBuildInputs:
    def test_requirements_are_pinned_and_shipped(self):
        requirements = (BASE_DIR / "requirements.txt").read_text().splitlines()
        packages = {
            line.split("==")[0].split("[")[0].lower()
            for line in requirements
            if line.strip() and not line.startswith("#")
        }

        for package in (
            "django",
            "djangorestframework",
            "django-axes",
            "gunicorn",
            "whitenoise",
            "dj-database-url",
        ):
            assert package in packages, package
        # A pinned list must not silently contain an unpinned entry.
        assert all("==" in line for line in requirements if line.strip() and not line.startswith("#"))

    def test_bootstrap_admin_command_exists(self):
        from django.core.management import get_commands

        assert get_commands().get("bootstrap_admin") == "stock_manager"
