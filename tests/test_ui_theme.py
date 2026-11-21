"""
Guards for the SAP Fiori style interface and the username/password sign-in.

The page script drives the UI through element ids and the ``d-none`` utility
class, so a renamed id or a stylesheet that stops being served breaks the
application silently. These tests pin the contract:

* the login page is a username + password form styled by the theme,
* the dashboard renders the shell bar, KPI tiles and every id the script uses,
* the theme ships the ``d-none`` utility and is discoverable by staticfiles,
* a lockout renders the branded page (still HTTP 429).
"""

import re

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders

pytestmark = pytest.mark.django_db

LOGIN_URL = "/accounts/login/"
STYLESHEET = "css/ssm-sap.css"


class TestLoginPage:
    def test_is_a_username_password_form_with_the_theme(self, client):
        html = client.get(LOGIN_URL).content.decode()

        assert STYLESHEET in html
        assert 'name="username"' in html
        assert 'name="password"' in html
        assert 'type="submit"' in html
        assert "bootstrap" not in html.lower()

    def test_has_csrf_token_and_password_toggle(self, client):
        html = client.get(LOGIN_URL).content.decode()

        assert "csrfmiddlewaretoken" in html
        assert "togglePassword" in html

    def test_failed_login_shows_an_error_strip_and_keeps_the_username(
        self, client, shop_user
    ):
        response = client.post(
            LOGIN_URL, {"username": "shop1", "password": "wrong-password"}
        )
        html = response.content.decode()

        assert response.status_code == 200
        assert "sap-msgstrip--error" in html
        assert 'value="shop1"' in html


class TestDashboardTheme:
    def test_renders_the_shell_bar_and_all_tables(self, client, shop_user, app_config):
        client.force_login(shop_user)
        html = client.get("/").content.decode()

        assert STYLESHEET in html
        assert 'class="sap-shellbar"' in html
        for marker in (
            'id="itemTable1"',
            'id="itemTable2"',
            'id="itemTable3"',
            'id="searchBox1"',
            'id="searchBox2"',
            'id="searchBox3"',
            'id="paginationControls1"',
            'id="paginationControls2"',
            'id="paginationControls3"',
            'id="updateModeToggle"',
            'id="submitTransferRequest"',
            'id="addItemSection"',
            'id="uploadStockDataButton"',
            'id="downloadStockData"',
            'id="change_pw_link"',
        ):
            assert marker in html, marker
        assert "bootstrap" not in html.lower()

    def test_every_id_the_page_script_selects_exists(self, client, shop_user, app_config):
        """A renamed element id would break the UI without any server error."""
        client.force_login(shop_user)
        html = client.get("/").content.decode()
        script = html.rsplit("<script>", 1)[-1]

        selected = set(
            re.findall(r"""\$\(\s*['"]#([A-Za-z][A-Za-z0-9_-]*)['"]""", script)
        )
        assert selected, "expected the page script to select elements by id"

        missing = sorted(i for i in selected if f'id="{i}"' not in html)
        assert missing == []


class TestStylesheet:
    def test_is_discoverable_by_staticfiles(self):
        assert finders.find(STYLESHEET) is not None

    def test_ships_the_dnone_utility_the_script_depends_on(self):
        path = finders.find(STYLESHEET)
        with open(path, encoding="utf-8") as handle:
            css = handle.read()

        assert ".d-none" in css
        assert "display: none !important" in css


class TestPasswordChangePages:
    def test_form_is_styled_by_the_theme(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/accounts/password_change/")

        assert response.status_code == 200
        html = response.content.decode()
        assert STYLESHEET in html
        assert 'name="old_password"' in html
        assert 'name="new_password1"' in html
        assert 'name="new_password2"' in html

    def test_done_page_uses_the_portal_template(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/accounts/password_change/done/")

        assert response.status_code == 200
        assert "registration/portal_password_change_done.html" in [
            template.name for template in response.templates
        ]


class TestLockoutPage:
    def test_renders_the_branded_lockout_page(self, client, shop_user, settings):
        settings.AXES_ENABLED = True
        for _ in range(3):
            client.post(LOGIN_URL, {"username": "shop1", "password": "wrong-password"})

        response = client.post(
            LOGIN_URL, {"username": "shop1", "password": "test-pass-123"}
        )
        html = response.content.decode()

        assert response.status_code == 429
        assert "Account temporarily locked" in html
        assert STYLESHEET in html
