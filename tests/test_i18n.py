"""Bilingual interface: English (LTR) and Arabic (RTL)."""

import re

import pytest
from django.utils import translation

from stock_manager.ui_strings import js_messages

pytestmark = pytest.mark.django_db


def dashboard(client, user, language):
    client.force_login(user)
    return client.get("/", headers={"accept-language": language}).content.decode()


def visible_markup(html):
    """The page without scripts, comments or attributes (ids/classes stay English)."""
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return html


class TestLanguageSelection:
    def test_english_is_left_to_right(self, client, manager, app_config):
        html = dashboard(client, manager, "en")

        assert 'lang="en"' in html
        assert 'dir="ltr"' in html
        assert "Warehouse stock" in html
        assert 'id="languageSelect"' in html

    def test_arabic_is_right_to_left_and_translated(self, client, manager, app_config):
        html = dashboard(client, manager, "ar")

        assert 'lang="ar"' in html
        assert 'dir="rtl"' in html
        # Headings, navigation and table headers all come from the catalog.
        assert "مخزون المخزن" in html
        assert "ملصقات الباركود" in html
        assert "استلام من المورد (أمر شراء)" in html
        assert "Warehouse stock" not in visible_markup(html)
        assert "Barcode labels" not in visible_markup(html)

    def test_the_switch_sets_the_cookie_and_returns_to_the_page(self, client, manager):
        client.force_login(manager)

        response = client.post("/i18n/set-language/", {"language": "ar", "next": "/"})

        assert response.status_code == 302
        assert response["Location"] == "/"
        assert response.cookies["django_language"].value == "ar"

    def test_the_switch_refuses_an_off_site_redirect(self, client, manager):
        client.force_login(manager)

        response = client.post(
            "/i18n/set-language/", {"language": "ar", "next": "https://evil.example/"}
        )

        assert response["Location"] == "/"

    def test_an_unknown_language_does_not_change_the_cookie(self, client, manager):
        client.force_login(manager)

        response = client.post("/i18n/set-language/", {"language": "xx", "next": "/"})

        assert "django_language" not in response.cookies


class TestCatalog:
    def test_every_msgid_has_an_arabic_translation(self):
        """A missing string would silently ship as English on the Arabic UI."""
        from scripts.build_messages import ARABIC, collect_msgids

        missing = [msgid for msgid in collect_msgids() if msgid not in ARABIC]

        assert missing == []

    def test_the_catalog_is_compiled_for_django(self):
        from pathlib import Path

        mo = Path("locale/ar/LC_MESSAGES/django.mo")
        assert mo.exists() and mo.stat().st_size > 0

        with translation.override("ar"):
            assert translation.gettext("Warehouse stock") == "مخزون المخزن"

    def test_the_script_gets_a_translation_map(self):
        with translation.override("ar"):
            messages = js_messages()

        assert messages["Hello"] == "أهلًا"
        assert messages["No records"] == "لا توجد سجلات"

    def test_english_needs_no_map(self):
        with translation.override("en"):
            assert js_messages() == {}


class TestTerminology:
    """The interface speaks about sites, never shops."""

    def test_no_shop_wording_is_rendered(self, client, manager, app_config):
        for language in ("en", "ar"):
            assert "shop" not in visible_markup(dashboard(client, manager, language)).lower()
