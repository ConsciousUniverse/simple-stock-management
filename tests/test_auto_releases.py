"""The update the phones are offered is read from where the builds are kept.

The manual page was a second place to keep the same fact, and a build could be
published to GitHub while every phone was still told about the older one. These
tests pin the reading rules: which number a tag means, which release wins, and
what happens when GitHub cannot be reached.
"""

from unittest.mock import patch

import pytest

from stock_manager import releases
from stock_manager.models import AppRelease


def release(tag, name="", assets=(), draft=False, prerelease=False, body=""):
    return {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": "2026-11-22T12:00:00Z",
        "assets": list(assets),
    }


def apk(name, size=5_700_000, digest=None):
    return {
        "name": name,
        "size": size,
        "digest": digest,
        "browser_download_url": f"https://github.com/x/y/releases/download/t/{name}",
    }


@pytest.fixture(autouse=True)
def clean_cache():
    releases.clear_cache()
    yield
    releases.clear_cache()


class TestTheBuildNumberInATag:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("v2", 2),
            ("V10", 10),
            ("warehouse-2.apk", 2),
            ("Warehouse 1.1.0 (build 2)", 2),
            ("build 7", 7),
            ("1.1.0", None),  # a dotted version cannot be ordered
            ("warehouse-latest.apk", None),
            ("", None),
            (None, None),
        ],
    )
    def test_reads_only_a_build_number(self, text, expected):
        assert releases.parse_version_code(text) == expected


class TestChoosingTheRelease:
    def test_the_highest_build_wins_not_the_newest_published(self):
        # The older tag was re-published last; the app compares NUMBERS.
        payload = [
            release("v1", assets=[apk("warehouse-1.apk")]),
            release("v3", assets=[apk("warehouse-3.apk")]),
        ]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            chosen = releases.latest_release()

        assert chosen["versionCode"] == 3
        assert chosen["downloadUrl"].endswith("warehouse-3.apk")
        assert chosen["source"] == "github"

    def test_a_draft_or_prerelease_is_not_offered(self):
        payload = [
            release("v2", assets=[apk("warehouse-2.apk")]),
            release("v9", assets=[apk("warehouse-9.apk")], draft=True),
            release("v8", assets=[apk("warehouse-8.apk")], prerelease=True),
        ]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            assert releases.latest_release()["versionCode"] == 2

    def test_a_release_without_an_apk_is_not_a_build(self):
        payload = [
            release("v2", assets=[apk("warehouse-2.apk")]),
            release("v5", assets=[{"name": "notes.txt", "size": 10}]),
        ]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            assert releases.latest_release()["versionCode"] == 2

    def test_the_checksum_and_size_come_from_the_asset(self):
        payload = [
            release(
                "v2",
                assets=[apk("warehouse-2.apk", 5_726_658, "sha256:" + "a" * 64)],
                body="notes",
            )
        ]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            chosen = releases.latest_release()

        assert chosen["sha256"] == "a" * 64
        assert chosen["sizeBytes"] == 5_726_658
        assert chosen["notes"] == "notes"

    def test_a_published_build_with_no_number_is_shown_not_offered(self):
        payload = [release("latest", assets=[apk("warehouse-latest.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            chosen = releases.latest_release()

        assert chosen["versionCode"] is None
        assert chosen["downloadUrl"].endswith("warehouse-latest.apk")


@pytest.mark.django_db
class TestWhenGithubCannotBeReached:
    """A failed read falls back to the mirror, which lives in the database."""
    def test_a_failure_returns_none_and_does_not_raise(self):
        with patch.object(
            releases,
            "_fetch_releases",
            side_effect=releases.ReleaseFetchError(releases.ERROR_UNREACHABLE),
        ):
            assert releases.latest_release() is None
        assert releases.last_error() == releases.ERROR_UNREACHABLE

    def test_a_failure_is_remembered_so_a_hundred_phones_do_not_retry(self):
        with patch.object(
            releases,
            "_fetch_releases",
            side_effect=releases.ReleaseFetchError(releases.ERROR_UNREACHABLE),
        ) as fetch:
            releases.latest_release()
            releases.latest_release()
            releases.latest_release()

        assert fetch.call_count == 1

    def test_a_success_is_cached_for_ten_minutes(self):
        payload = [release("v2", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload) as fetch:
            releases.latest_release()
            releases.latest_release()

        assert fetch.call_count == 1


@pytest.mark.django_db
class TestWhatTheAppIsTold:
    def test_the_app_is_offered_the_published_build(self):
        payload = [release("v2", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            from stock_manager import mobile

            told = mobile.version_payload(1)

        assert told["updateAvailable"] is True
        assert told["latest"]["versionCode"] == 2
        assert told["latest"]["sha256"] == ""

    def test_a_phone_on_the_newest_build_is_told_nothing(self):
        payload = [release("v2", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            from stock_manager import mobile

            told = mobile.version_payload(2)

        assert told["updateAvailable"] is False
        assert told["latest"]["current"] is True

    def test_the_manual_row_is_used_when_github_cannot_be_read(self):
        AppRelease.objects.create(
            version="9.9.9",
            version_code=99,
            download_url="https://example.test/app.apk",
            mandatory=True,
        )
        with patch.object(
            releases,
            "_fetch_releases",
            side_effect=releases.ReleaseFetchError(releases.ERROR_UNREACHABLE),
        ):
            from stock_manager import mobile

            told = mobile.version_payload(1)

        assert told["latest"]["versionCode"] == 99
        assert told["latest"]["mandatory"] is True

    def test_a_higher_manual_pin_beats_an_older_tag_still_on_github(self):
        AppRelease.objects.create(
            version="3.0.0",
            version_code=30,
            download_url="https://example.test/app.apk",
        )
        payload = [release("v2", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            from stock_manager import mobile

            assert mobile.version_payload(1)["latest"]["versionCode"] == 30

    def test_an_older_manual_row_does_not_hide_the_newer_published_build(self):
        AppRelease.objects.create(
            version="1.0.0",
            version_code=1,
            download_url="https://example.test/app.apk",
        )
        payload = [release("v2", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            from stock_manager import mobile

            assert mobile.version_payload(1)["latest"]["versionCode"] == 2

    def test_with_no_release_anywhere_the_app_is_told_nothing(self):
        with patch.object(releases, "_fetch_releases", return_value=[]):
            from stock_manager import mobile

            told = mobile.version_payload(1)
            assert told["updateAvailable"] is False
            assert told["latest"] is None


@pytest.mark.django_db
class TestTheAndroidPage:
    """The page must show the build the app is actually told about."""

    def test_the_page_shows_the_build_read_from_github(self, client, manager):
        client.force_login(manager)
        payload = [release("v2", name="Warehouse 1.1.0 (build 2)", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            page = client.get("/android/")

        body = page.content.decode()
        assert "Warehouse 1.1.0 (build 2)" in body
        assert "warehouse-2.apk" in body
        assert "autoReleaseUnavailable" not in body

    def test_the_page_says_so_when_the_list_cannot_be_read(self, client, manager):
        client.force_login(manager)
        with patch.object(
            releases,
            "_fetch_releases",
            side_effect=releases.ReleaseFetchError(releases.ERROR_UNREACHABLE),
        ):
            page = client.get("/android/")

        body = page.content.decode()
        assert "autoReleaseUnavailable" in body
        # and it still tells the reader which build the phones are offered
        assert "No build has been published yet." in body


@pytest.mark.django_db
class TestAFailureIsNotAnAbsence:
    """`there is no update` and `the list could not be read` are opposites."""

    def test_a_rate_limited_answer_is_not_read_as_an_empty_list(self):
        with patch.object(
            releases,
            "_fetch_releases",
            side_effect=releases.ReleaseFetchError(releases.ERROR_RATE_LIMITED),
        ):
            assert releases.latest_release() is None
        assert releases.last_error() == releases.ERROR_RATE_LIMITED

    def test_an_error_object_is_a_failure_not_an_empty_list(self):
        # GitHub answers an error with {"message": ...}; a list-only reader that
        # treated it as [] would tell every phone there is nothing to install.
        def not_a_list():
            raise releases.ReleaseFetchError(releases.ERROR_BAD_RESPONSE, "API rate limit")

        with patch.object(releases, "_fetch_releases", side_effect=not_a_list):
            releases.latest_release()

        assert releases.last_error() == releases.ERROR_BAD_RESPONSE

    def test_a_defect_in_the_reader_still_answers_from_the_mirror(self):
        from stock_manager.models import AppRelease

        AppRelease.objects.create(
            version="1.1.0",
            version_code=2,
            download_url="https://example.test/app.apk",
            source=AppRelease.SOURCE_GITHUB,
        )
        with patch.object(releases, "_fetch_releases", side_effect=RuntimeError("bug")):
            chosen = releases.latest_release()

        assert chosen["versionCode"] == 2
        assert chosen["source"] == "cache"

    def test_a_successful_read_is_mirrored_and_serves_an_outage(self):
        from stock_manager.models import AppRelease

        payload = [release("v2", assets=[apk("warehouse-2.apk")])]
        with patch.object(releases, "_fetch_releases", return_value=payload):
            releases.latest_release()

        row = AppRelease.objects.get(version_code=2)
        assert row.source == AppRelease.SOURCE_GITHUB

        releases.clear_cache()
        with patch.object(
            releases,
            "_fetch_releases",
            side_effect=releases.ReleaseFetchError(releases.ERROR_UNREACHABLE),
        ):
            from stock_manager import mobile

            told = mobile.version_payload(1)

        # The outage must not read as "nothing to install".
        assert told["updateAvailable"] is True
        assert told["latest"]["versionCode"] == 2
        assert told["releaseSource"] == "cache"
        assert told["releaseError"] == releases.ERROR_UNREACHABLE

    def test_a_mirrored_row_is_never_a_manual_pin(self):
        from stock_manager.models import AppRelease

        AppRelease.objects.create(
            version="9.9.9",
            version_code=99,
            download_url="https://example.test/app.apk",
            source=AppRelease.SOURCE_GITHUB,
        )
        assert AppRelease.latest_manual() is None
