"""The Android app page: one published build, and where it comes from.

The address is stored rather than the file: the deployment's disk is wiped on
every release, so an uploaded APK would vanish and the download button would
keep pointing at nothing.
"""

import pytest
from rest_framework.test import APIClient

from stock_manager.models import AppRelease, AuditEvent

pytestmark = pytest.mark.django_db


def publish(client, version_code=1, **fields):
    data = {
        "version": "1.0.1",
        "download_url": "https://example.com/app.apk",
        "version_code": str(version_code),
    }
    data.update(fields)
    return client.post("/android/", data, follow=True)


class TestThePage:
    def test_every_user_may_open_it(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/android/")
        assert response.status_code == 200
        assert b"apiRoot" in response.content

    def test_it_shows_an_empty_state_before_anything_is_published(
        self, client, shop_user
    ):
        client.force_login(shop_user)
        response = client.get("/android/")
        assert response.context["latest"] is None
        assert b"releasesTable" in response.content

    def test_the_current_build_is_offered_for_download(self, client, manager):
        AppRelease.objects.create(
            version="2.0.0",
            download_url="https://example.com/v2.apk",
            notes="Faster labels",
            created_by=manager,
        )
        client.force_login(manager)

        response = client.get("/android/")

        assert response.context["latest"].version == "2.0.0"
        assert b"https://example.com/v2.apk" in response.content

    def test_a_shop_user_sees_no_publish_form(self, client, shop_user):
        client.force_login(shop_user)
        response = client.get("/android/")
        assert b"publishReleaseForm" not in response.content


class TestPublishing:
    def test_a_manager_publishes_a_build(self, client, manager):
        client.force_login(manager)

        response = publish(client, version="1.0.1", notes="First build")

        assert response.status_code == 200
        release = AppRelease.objects.get(version="1.0.1")
        assert release.is_current is True
        assert release.created_by == manager
        assert AuditEvent.objects.filter(action=AuditEvent.RELEASE_PUBLISHED).exists()

    def test_a_shop_user_cannot_publish(self, client, shop_user):
        client.force_login(shop_user)

        publish(client, version="9.9.9")

        assert not AppRelease.objects.filter(version="9.9.9").exists()

    def test_only_one_build_stays_current(self, client, manager):
        client.force_login(manager)

        publish(client, version_code=1, version="1.0.1")
        publish(
            client,
            version_code=2,
            version="1.0.2",
            download_url="https://example.com/v2.apk",
        )

        assert AppRelease.objects.filter(is_current=True).count() == 1
        assert AppRelease.objects.get(is_current=True).version == "1.0.2"

    def test_a_duplicate_version_is_refused(self, client, manager):
        client.force_login(manager)
        publish(client, version_code=1, version="1.0.1")

        response = publish(client, version_code=2, version="1.0.1")

        assert AppRelease.objects.filter(version="1.0.1").count() == 1
        assert "already published" in response.content.decode()

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "example.com/app.apk",
            "ftp://example.com/app.apk",
            "",
        ],
    )
    def test_an_address_a_phone_cannot_open_is_refused(self, client, manager, url):
        client.force_login(manager)

        response = publish(client, version_code=1, version="1.0.1", download_url=url)

        assert not AppRelease.objects.filter(version="1.0.1").exists()
        assert "must start with" in response.content.decode()

    def test_a_path_on_this_site_is_accepted(self, client, manager):
        client.force_login(manager)

        publish(client, version_code=1, version="1.0.1", download_url="/media/app.apk")

        assert AppRelease.objects.get(version="1.0.1").download_url == "/media/app.apk"

    def test_an_empty_version_is_refused(self, client, manager):
        client.force_login(manager)

        publish(client, version_code=1, version="   ")

        assert AppRelease.objects.count() == 0


class TestTheBuildNumber:
    """The app compares numbers: a release without one is never an update."""

    def test_a_build_without_a_number_is_refused(self, client, manager):
        client.force_login(manager)

        response = client.post(
            "/android/",
            {"version": "1.0.1", "download_url": "https://example.com/a.apk"},
            follow=True,
        )

        assert not AppRelease.objects.filter(version="1.0.1").exists()
        assert "build number" in response.content.decode()

    def test_a_build_number_that_does_not_grow_is_refused(self, client, manager):
        client.force_login(manager)
        publish(client, version_code=7, version="1.0.7")

        response = publish(client, version_code=7, version="1.0.6")

        assert not AppRelease.objects.filter(version="1.0.6").exists()
        assert "higher than 7" in response.content.decode()

    def test_the_number_checksum_and_flag_are_stored(self, client, manager):
        client.force_login(manager)
        digest = "a" * 64

        publish(
            client,
            version_code=3,
            version="1.0.3",
            sha256=digest,
            size_bytes="123456",
            mandatory="on",
        )

        release = AppRelease.objects.get(version="1.0.3")
        assert release.version_code == 3
        assert release.sha256 == digest
        assert release.size_bytes == 123456
        assert release.mandatory is True

    def test_a_checksum_that_is_not_a_checksum_is_refused(self, client, manager):
        client.force_login(manager)

        response = publish(client, version_code=1, version="1.0.1", sha256="abc")

        assert not AppRelease.objects.filter(version="1.0.1").exists()
        assert "64 hexadecimal" in response.content.decode()


class TestTheAppConfigEndpoint:
    def test_it_tells_the_app_which_build_is_newest(self, manager):
        AppRelease.objects.create(
            version="3.1.4", download_url="https://example.com/v3.apk"
        )
        client = APIClient()
        client.force_authenticate(user=manager)

        payload = client.get("/api/app_config/").json()

        assert payload["latest_app_version"] == "3.1.4"
        assert payload["app_download_url"] == "https://example.com/v3.apk"

    def test_it_says_so_when_nothing_is_published(self, manager):
        client = APIClient()
        client.force_authenticate(user=manager)

        payload = client.get("/api/app_config/").json()

        assert payload["latest_app_version"] is None
        assert payload["app_download_url"] is None
