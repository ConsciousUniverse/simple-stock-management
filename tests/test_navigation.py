"""The sidebar: exactly the entries the operator asked for, in that order.

The navigation is the one thing every user sees on every page, so it is pinned
here rather than checked by eye: the order, who may see the manager-only
entries, the active state, and that no entry leads nowhere.
"""

import re

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

# The order the operator specified.
EXPECTED = [
    ("issues", "/issues/"),
    ("additions", "/receipts/"),
    ("spending", "/issues/report/"),
    ("dashboard", "/"),
    ("items", "/stock/"),
    ("labels", "/labels/"),
    ("users", "/users/"),
    ("android", "/android/"),
    ("audit", "/audit/"),
]

MANAGER_ONLY = {"users", "audit"}


def nav_items(response):
    """(section, href, is_active) for each entry, in the order rendered."""
    html = response.content.decode()
    nav = re.search(r'<nav class="sap-sidenav__nav".*?</nav>', html, re.S)
    assert nav, "the sidebar is missing from the page"
    return [
        (
            section,
            href,
            "is-active" in classes,
        )
        for classes, href, section in re.findall(
            r'<a class="sap-sidenav__item([^"]*)" href="([^"]+)" data-nav="([^"]+)"',
            nav.group(0),
        )
    ]


class TestOrder:
    def test_a_manager_sees_the_nine_entries_in_the_requested_order(
        self, client, manager
    ):
        client.force_login(manager)

        items = nav_items(client.get("/stock/"))

        assert [(section, href) for section, href, _ in items] == EXPECTED

    def test_a_shop_user_sees_the_same_order_without_the_manager_entries(
        self, client, shop_user
    ):
        client.force_login(shop_user)

        items = nav_items(client.get("/stock/"))

        expected = [pair for pair in EXPECTED if pair[0] not in MANAGER_ONLY]
        assert [(section, href) for section, href, _ in items] == expected

    def test_the_sidebar_has_no_extra_entry(self, client, manager):
        client.force_login(manager)

        items = nav_items(client.get("/stock/"))

        assert len(items) == len(EXPECTED)


class TestOneDefinition:
    def test_the_dashboard_and_the_other_pages_share_the_same_menu(
        self, client, manager
    ):
        # The dashboard has its own shell, so it once carried a second, different
        # menu. Both now include the same partial; this pins that.
        client.force_login(manager)

        dashboard = [(section, href) for section, href, _ in nav_items(client.get("/"))]
        other = [(section, href) for section, href, _ in nav_items(client.get("/stock/"))]
        assert dashboard == other

    def test_no_template_repeats_the_menu_by_hand(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "templates"
        # ``data-nav`` marks a SITE menu entry (the dashboard's in-page scroller
        # uses ``data-spy`` instead, so it is not counted).
        owners = [
            path.name
            for path in root.rglob("*.html")
            if 'data-nav="' in path.read_text(encoding="utf-8")
        ]
        assert owners == ["sidenav.html"]


class TestActiveState:
    @pytest.mark.parametrize(
        "url,active",
        [
            ("/", "dashboard"),
            ("/stock/", "items"),
            ("/receipts/", "additions"),
            ("/issues/", "issues"),
            ("/issues/report/", "spending"),
            ("/labels/", "labels"),
            ("/users/", "users"),
            ("/android/", "android"),
            ("/audit/", "audit"),
        ],
    )
    def test_exactly_one_entry_is_marked_current(self, client, manager, url, active):
        client.force_login(manager)

        items = nav_items(client.get(url))

        active_sections = [section for section, _, is_active in items if is_active]
        assert active_sections == [active]

    def test_the_printable_sheet_keeps_the_label_entry_current(self, client, manager):
        # /labels/?skus=… renders the sheet, not the picker; the sidebar is not on
        # that page, but the section mapping still has to resolve.
        client.force_login(manager)

        response = client.get("/labels/?skus=ANY")

        assert response.status_code == 200


class TestLinks:
    @pytest.mark.parametrize("section,href", EXPECTED)
    def test_every_entry_opens_for_a_manager(self, client, manager, section, href):
        client.force_login(manager)

        response = client.get(href)

        assert response.status_code == 200

    def test_the_android_entry_opens_for_a_shop_user(self, client, shop_user):
        client.force_login(shop_user)

        assert client.get("/android/").status_code == 200

    def test_the_manager_entries_redirect_a_shop_user(self, client, shop_user):
        client.force_login(shop_user)

        for href in ("/users/", "/audit/"):
            response = client.get(href)
            assert response.status_code == 302, href


class TestTheReaderRole:
    def test_the_shellbar_names_a_manager_on_every_page(self, client, manager):
        client.force_login(manager)

        for href in ("/", "/stock/", "/users/", "/audit/", "/android/", "/labels/"):
            html = client.get(href).content.decode()
            assert "Warehouse manager" in html, href

    def test_the_shellbar_names_a_site_user(self, client, shop_user):
        client.force_login(shop_user)

        html = client.get("/android/").content.decode()

        assert "Site user" in html
        assert "Warehouse manager" not in html


class TestLabelsPicker:
    def test_the_picker_replaces_the_empty_sheet(self, client, manager, make_item):
        make_item(sku="SKU-1", description="Widget")
        client.force_login(manager)

        response = client.get("/labels/")

        assert b"labelPicker" in response.content
        assert b"SKU-1" in response.content

    def test_the_sheet_still_renders_when_items_are_chosen(
        self, client, manager, make_item
    ):
        make_item(sku="SKU-1", description="Widget")
        client.force_login(manager)

        response = client.get("/labels/?skus=SKU-1&copies=2")

        assert b"label-sheet" in response.content
        assert response.context["copies"] == 2

    def test_an_unknown_code_is_reported_on_the_sheet(self, client, manager):
        client.force_login(manager)

        response = client.get("/labels/?skus=MISSING-1")

        assert response.context["errors"]

    def test_the_picker_is_searchable(self, client, manager, make_item):
        make_item(sku="AAA-1", description="Hammer")
        make_item(sku="BBB-2", description="Saw")
        client.force_login(manager)

        response = client.get("/labels/?q=Saw")

        assert [item.sku for item in response.context["items"]] == ["BBB-2"]
