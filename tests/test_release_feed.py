"""The build is read from the release pages when the API refuses.

Production measured this: GitHub's anonymous API allows 60 requests an hour
**per IP**, Render's egress is shared, and the server answered ``rate_limited``
while build 3 was published — so every phone was offered build 2. The public
pages (the atom feed and the asset list) are not the API, so a spent budget must
not hide a build.
"""

import pytest

from stock_manager import releases
from stock_manager.models import AppRelease

pytestmark = pytest.mark.django_db

SHA = "334dfbe2f90eea480ec66ae57496aaaa1badee7cccd800bf209c02e9e0c1161e"

FEED = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Release notes from warehouse-app-releases</title>
  <entry>
    <id>tag:github.com,2008:Repository/1/v3</id>
    <updated>2026-11-22T15:22:18Z</updated>
    <link rel="alternate" type="text/html" href="https://github.com/melsofany/warehouse-app-releases/releases/tag/v3"/>
    <title>Warehouse 1.2.0 (build 3)</title>
    <content type="html">&lt;p&gt;The launcher icon is the company mark.&lt;/p&gt;
&lt;p&gt;SHA-256: {SHA}&lt;br&gt;
Size: 5801166 bytes&lt;/p&gt;</content>
  </entry>
  <entry>
    <id>tag:github.com,2008:Repository/1/v2</id>
    <updated>2026-11-20T10:00:00Z</updated>
    <link rel="alternate" type="text/html" href="https://github.com/melsofany/warehouse-app-releases/releases/tag/v2"/>
    <title>Warehouse 1.1.0 (build 2)</title>
    <content type="html">&lt;p&gt;Older build.&lt;/p&gt;</content>
  </entry>
</feed>
"""

ASSETS = """
<div class="Box">
  <a href="/melsofany/warehouse-app-releases/releases/download/v3/warehouse-3.apk"
     rel="nofollow" class="text-bold">warehouse-3.apk</a>
  <span>5.53 MB</span>
</div>
"""

ASSETS_V2 = """
<div class="Box">
  <a href="/melsofany/warehouse-app-releases/releases/download/v2/warehouse-2.apk"
     rel="nofollow" class="text-bold">warehouse-2.apk</a>
</div>
"""


@pytest.fixture
def pages(monkeypatch):
    """The public pages, keyed by URL — nothing reaches the network."""

    def _get(url, timeout):
        if url.endswith("releases.atom"):
            return FEED
        if "/expanded_assets/v3" in url:
            return ASSETS
        if "/expanded_assets/v2" in url:
            return ASSETS_V2
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(releases, "_get", _get)
    return _get


class TestTheFeedReader:
    def test_it_reads_the_newest_numbered_build(self, pages):
        value = releases._feed_release()

        assert value["versionCode"] == 3
        assert value["versionName"] == "Warehouse 1.2.0 (build 3)"
        assert value["downloadUrl"].endswith("/v3/warehouse-3.apk")
        assert value["sha256"] == SHA
        assert value["sizeBytes"] == 5801166
        assert value["source"] == "feed"

    def test_a_feed_with_no_asset_is_not_a_release(self, monkeypatch):
        monkeypatch.setattr(
            releases, "_get", lambda url, timeout: FEED.replace("v3", "v9")
        )
        # v9 has no asset page, so there is nothing to install.
        with pytest.raises(releases.ReleaseFetchError):
            releases._feed_release()

    def test_an_empty_feed_is_an_error_not_an_empty_answer(self, monkeypatch):
        monkeypatch.setattr(releases, "_get", lambda url, timeout: "<feed></feed>")
        with pytest.raises(releases.ReleaseFetchError):
            releases._feed_release()


class TestTheFallback:
    def test_a_rate_limited_api_still_offers_the_new_build(
        self, monkeypatch, pages, client, shop_user
    ):
        def refuse():
            raise releases.ReleaseFetchError(releases.ERROR_RATE_LIMITED, "HTTP 403")

        monkeypatch.setattr(releases, "_fetch_releases", refuse)
        releases.clear_cache()

        response = client.get("/api/mobile/version/?code=2")

        payload = response.json()
        assert payload["updateAvailable"] is True
        assert payload["latest"]["versionCode"] == 3
        assert payload["latest"]["sha256"] == SHA
        # The read succeeded, so nothing is reported as broken.
        assert payload["releaseError"] is None

    def test_the_fallback_is_mirrored_for_the_next_outage(self, monkeypatch, pages):
        def refuse():
            raise releases.ReleaseFetchError(releases.ERROR_RATE_LIMITED, "HTTP 403")

        monkeypatch.setattr(releases, "_fetch_releases", refuse)
        releases.clear_cache()

        releases.latest_release(force=True)

        mirrored = AppRelease.objects.get(version_code=3)
        assert mirrored.download_url.endswith("/v3/warehouse-3.apk")

    def test_both_paths_failing_serves_the_mirror_and_says_so(
        self, monkeypatch, client, shop_user
    ):
        AppRelease.objects.create(
            version="1.1.0",
            version_code=2,
            download_url="https://example.com/warehouse-2.apk",
            source=AppRelease.SOURCE_GITHUB,
        )

        def refuse():
            raise releases.ReleaseFetchError(releases.ERROR_RATE_LIMITED, "HTTP 403")

        monkeypatch.setattr(releases, "_fetch_releases", refuse)
        monkeypatch.setattr(
            releases,
            "_get",
            lambda url, timeout: (_ for _ in ()).throw(
                releases.ReleaseFetchError(releases.ERROR_UNREACHABLE, "offline")
            ),
        )
        releases.clear_cache()

        payload = client.get("/api/mobile/version/?code=1").json()

        assert payload["latest"]["versionCode"] == 2
        assert payload["releaseSource"] == "cache"
        assert payload["releaseError"] == releases.ERROR_RATE_LIMITED

    def test_a_working_api_is_never_second_guessed(self, monkeypatch):
        def explode(*args, **kwargs):
            raise AssertionError("the feed must not be read when the API works")

        monkeypatch.setattr(releases, "_get", explode)
        monkeypatch.setattr(
            releases,
            "_fetch_releases",
            lambda: [
                {
                    "tag_name": "v4",
                    "name": "Warehouse 1.3.0 (build 4)",
                    "body": "notes",
                    "published_at": "2026-11-23T00:00:00Z",
                    "assets": [
                        {
                            "name": "warehouse-4.apk",
                            "browser_download_url": "https://example.com/w4.apk",
                            "size": 10,
                        }
                    ],
                }
            ],
        )
        releases.clear_cache()

        assert releases.latest_release(force=True)["versionCode"] == 4
