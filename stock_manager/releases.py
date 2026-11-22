"""The newest Android build, read from the place the builds are actually kept.

The APK is not stored on this server: Render's disk is wiped on every deploy, so
a file written here disappears and the download link rots without a word. The
builds live as assets on a GitHub release, and this module reads that list — so
publishing a release IS publishing the update, with nothing to type into a page.

Three promises the code has to keep:

* **Nothing breaks when GitHub cannot be reached.** A phone asking "is there an
  update?" must get an answer during an outage, so every successful read is
  mirrored into ``AppRelease`` and served from there when the next read fails.
* **A failure is not "there is no update".** The two are opposite answers, and
  reporting the first as the second is how a published build goes uninstalled.
  ``last_error()`` names what happened, and the page shows it.
* **A build with no number is not silently dropped.** The app decides with
  ``versionCode``; a release whose tag carries no number cannot be compared, so
  it is returned as-is (with ``versionCode`` None) and shown on the page, rather
  than pretending nothing was published.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

#: Where the builds are published. Overridable so a fork does not edit code.
RELEASES_REPO = os.environ.get("APP_RELEASES_REPO", "melsofany/warehouse-app-releases")

#: One request per ten minutes serves every phone in the company: the answer is
#: the same for all of them, and GitHub's anonymous limit is per hour.
CACHE_SECONDS = 600

#: A failure is remembered for a shorter time: long enough that a hundred phones
#: do not each retry a broken connection, short enough that the next recovery is
#: noticed without a deploy.
FAILURE_SECONDS = 60

TIMEOUT_SECONDS = 5

#: What went wrong, in words the page can show. The distinction matters: a rate
#: limit clears by itself, an unreachable host is a network fault, and a body
#: that is not a list means GitHub answered with an error message.
ERROR_RATE_LIMITED = "rate_limited"
ERROR_UNREACHABLE = "unreachable"
ERROR_BAD_RESPONSE = "bad_response"

_BUILD_WORD = re.compile(r"\bbuild\s+(\d+)\b", re.IGNORECASE)

#: The public pages of the releases repository. They are NOT the API, which
#: matters: the anonymous API limit is 60 requests an hour **per IP**, and
#: Render's egress is shared — measured in production as ``rate_limited``, i.e.
#: a published build the phones were never told about.
FEED_URL = "https://github.com/{repo}/releases.atom"
ASSETS_URL = "https://github.com/{repo}/releases/expanded_assets/{tag}"
_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S)
_ENTRY_TAG = re.compile(r"/releases/tag/([^\"]+)")
_ENTRY_TITLE = re.compile(r"<title>([^<]*)</title>")
_ENTRY_UPDATED = re.compile(r"<updated>([^<]+)</updated>")
_ENTRY_BODY = re.compile(r'<content type="html">(.*?)</content>', re.S)
_ASSET_LINK = re.compile(r'href="([^"]*/releases/download/[^"]+\.apk)"')
_SHA_LINE = re.compile(r"SHA-?256[:\s]*([0-9a-fA-F]{64})")
_SIZE_LINE = re.compile(r"Size:\s*(\d+)\s*bytes", re.IGNORECASE)
_TRAILING_NUMBER = re.compile(r"[vV](\d+)$|[-_ ](\d+)$")
_cache = {"at": 0.0, "value": None, "ok": False, "error": None}


class ReleaseFetchError(Exception):
    """The release list could not be read, and why."""

    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


def parse_version_code(text):
    """The build number in a tag, a release name or an asset name, or None.

    ``v2``, ``warehouse-2.apk`` and ``Warehouse 1.1.0 (build 2)`` all mean 2.
    ``1.1.0`` means nothing: a dotted version cannot be ordered reliably, and a
    wrong number here offers an update that is not newer — or hides one that is.
    """
    if not text:
        return None
    value = str(text).strip()
    if value.lower().endswith(".apk"):
        value = value[:-4]
    found = _BUILD_WORD.search(value)
    if found:
        return int(found.group(1))
    found = _TRAILING_NUMBER.search(value)
    if found:
        return int(found.group(1) or found.group(2))
    return None


def _headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ssm-warehouse",
    }
    # Optional: an anonymous request is enough for a public releases repo, and a
    # token only raises the hourly limit.
    token = os.environ.get("GITHUB_RELEASES_TOKEN") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_releases():
    url = f"https://api.github.com/repos/{RELEASES_REPO}/releases?per_page=20"
    request = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # 403/429 is the anonymous hourly limit; the rest is GitHub refusing.
        kind = ERROR_RATE_LIMITED if exc.code in (403, 429) else ERROR_BAD_RESPONSE
        raise ReleaseFetchError(kind, f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ReleaseFetchError(ERROR_UNREACHABLE, str(exc)) from exc

    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ReleaseFetchError(ERROR_BAD_RESPONSE, "not JSON") from exc
    if not isinstance(payload, list):
        # GitHub answers an error with an OBJECT; reading that as "no releases"
        # would tell every phone there is nothing to install.
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise ReleaseFetchError(ERROR_BAD_RESPONSE, str(message)[:120])
    return payload


def _get(url, timeout):
    """One public page, with the failures classified the same way as the API."""
    request = urllib.request.Request(url, headers={"User-Agent": "ssm-warehouse"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        kind = ERROR_RATE_LIMITED if exc.code in (403, 429) else ERROR_BAD_RESPONSE
        raise ReleaseFetchError(kind, f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ReleaseFetchError(ERROR_UNREACHABLE, str(exc)) from exc


def _feed_release():
    """The newest build, read from the repository's public release pages.

    The atom feed carries the tag, the title, the date and the notes; the asset
    list carries the file. Neither is the API, so a shared egress IP that has
    spent its hourly API budget can still see a build that was published.
    """
    feed = _get(FEED_URL.format(repo=RELEASES_REPO), TIMEOUT_SECONDS * 2)
    entries = _ENTRY.findall(feed)
    if not entries:
        raise ReleaseFetchError(ERROR_BAD_RESPONSE, "no entries in the feed")

    best = None
    for entry in entries[:5]:
        tag = _ENTRY_TAG.search(entry)
        if not tag:
            continue
        tag = tag.group(1)
        found_title = _ENTRY_TITLE.search(entry)
        title = html.unescape(found_title.group(1)) if found_title else ""
        updated = _ENTRY_UPDATED.search(entry)
        body = _ENTRY_BODY.search(entry)
        body_text = html.unescape(body.group(1)) if body else ""

        page = _get(ASSETS_URL.format(repo=RELEASES_REPO, tag=tag), TIMEOUT_SECONDS * 2)
        link = _ASSET_LINK.search(page)
        if link is None:
            continue
        url = link.group(1)
        if url.startswith("/"):
            url = "https://github.com" + url

        code = parse_version_code(tag) or parse_version_code(title)
        if code is None:
            continue
        sha = _SHA_LINE.search(body_text)
        size = _SIZE_LINE.search(body_text)
        candidate = {
            "versionName": title or tag,
            "versionCode": code,
            "downloadUrl": url,
            "notes": body_text,
            "mandatory": False,
            "sha256": (sha.group(1).lower() if sha else ""),
            "sizeBytes": int(size.group(1)) if size else None,
            "publishedAt": updated.group(1) if updated else "",
            "source": "feed",
        }
        if best is None or (candidate["versionCode"] or 0) > (best["versionCode"] or 0):
            best = candidate
    if best is None:
        raise ReleaseFetchError(ERROR_BAD_RESPONSE, "no numbered release in the feed")
    return best


def _apk_asset(release):
    for asset in release.get("assets") or []:
        if str(asset.get("name", "")).lower().endswith(".apk"):
            return asset
    return None


def _sha256_of(asset):
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        return digest[len("sha256:") :].lower()
    return ""


def _as_release(release, source="github"):
    """One GitHub release as the shape the app and the page both read."""
    asset = _apk_asset(release)
    code = (
        parse_version_code(release.get("tag_name"))
        or parse_version_code(release.get("name"))
        or parse_version_code(asset.get("name") if asset else "")
    )
    return {
        "versionName": release.get("name") or release.get("tag_name") or "",
        "versionCode": code,
        "downloadUrl": (asset or {}).get("browser_download_url", ""),
        "notes": release.get("body") or "",
        "mandatory": False,
        "sha256": _sha256_of(asset or {}),
        "sizeBytes": (asset or {}).get("size"),
        "publishedAt": release.get("published_at") or "",
        "source": source,
    }


def remember_release(value):
    """Mirror a build into the database, so an outage cannot erase it.

    Best-effort on purpose: a phone asking about an update must not fail because
    the bookkeeping failed. The next successful read writes it again.
    """
    from stock_manager.models import AppRelease

    if not value or not value.get("versionCode"):
        return
    try:
        AppRelease.objects.update_or_create(
            version_code=value["versionCode"],
            defaults={
                "version": value["versionName"] or str(value["versionCode"]),
                "download_url": value["downloadUrl"],
                "sha256": value["sha256"],
                "size_bytes": value["sizeBytes"],
                "notes": value["notes"],
                "source": AppRelease.SOURCE_GITHUB,
            },
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping never fails a request
        logger.warning("The app release could not be mirrored: %s", exc)


def _mirrored_release():
    """The newest build this server has seen, from the mirror table."""
    from stock_manager.models import AppRelease

    row = (
        AppRelease.objects.filter(
            source=AppRelease.SOURCE_GITHUB, version_code__isnull=False
        )
        .order_by("-version_code")
        .first()
    )
    if row is None:
        return None
    return {
        "versionName": row.version,
        "versionCode": row.version_code,
        "downloadUrl": row.download_url,
        "notes": row.notes,
        "mandatory": False,
        "sha256": row.sha256 or "",
        "sizeBytes": row.size_bytes,
        "publishedAt": row.created_at.isoformat(),
        "source": "cache",
    }


def _serve_mirror(now, kind):
    try:
        mirrored = _mirrored_release()
    except Exception as exc:  # noqa: BLE001 - the endpoint must still answer
        logger.warning("The mirrored app release could not be read: %s", exc)
        mirrored = None
    _cache.update({"at": now, "value": mirrored, "ok": False, "error": kind})
    return mirrored


def last_error():
    """Why the last read failed, or None when it did not."""
    return _cache["error"]


def latest_release(force=False):
    """The newest published build with an APK, or None when none can be read."""
    now = time.time()
    age = now - _cache["at"]
    fresh_for = CACHE_SECONDS if _cache["ok"] else FAILURE_SECONDS
    if not force and _cache["at"] and age < fresh_for:
        return _cache["value"]

    try:
        raw = _fetch_releases()
    except ReleaseFetchError as exc:
        # The API refused (usually the shared hourly limit) — the public pages
        # still answer, so a build published today is still delivered today.
        logger.warning("App releases could not be read from %s: %s", RELEASES_REPO, exc)
        try:
            value = _feed_release()
        except ReleaseFetchError as feed_exc:
            logger.warning("The release feed failed too: %s", feed_exc)
            return _serve_mirror(now, exc.kind)
        logger.info(
            "App release %s read from the release feed", value.get("versionName")
        )
        remember_release(value)
        _cache.update({"at": now, "value": value, "ok": True, "error": None})
        return value
    except Exception as exc:  # noqa: BLE001 - a public endpoint must answer
        # A defect in the reader is still not "there is no update": fall back to
        # the mirror and say the read failed, rather than answering 500.
        logger.exception("Reading the app releases failed: %s", exc)
        return _serve_mirror(now, ERROR_BAD_RESPONSE)

    usable = [
        release
        for release in raw
        if not release.get("draft")
        and not release.get("prerelease")
        and _apk_asset(release) is not None
    ]
    numbered = [release for release in usable if _as_release(release)["versionCode"]]
    if numbered:
        newest = max(numbered, key=lambda release: _as_release(release)["versionCode"])
        value = _as_release(newest)
    elif usable:
        # Published, but with no number to compare: shown, never offered as an
        # update. Newest first is how GitHub returns them.
        value = _as_release(usable[0])
    else:
        value = None

    if value:
        remember_release(value)
    _cache.update({"at": now, "value": value, "ok": True, "error": None})
    return value


def _manual_release():
    from stock_manager.models import AppRelease

    row = AppRelease.latest_manual()
    if row is None:
        return None
    return {
        "versionName": row.version,
        "versionCode": row.version_code,
        "downloadUrl": row.download_url,
        "notes": row.notes,
        "mandatory": bool(row.mandatory),
        "sha256": row.sha256 or "",
        "sizeBytes": row.size_bytes,
        "publishedAt": row.created_at.isoformat(),
        "source": "manual",
    }


def select_release():
    """The build the phones are offered.

    The published release wins — that is the point of reading it — except when a
    manager has recorded a build with a HIGHER number by hand, which is a
    deliberate pin and must not be undone by an older tag still on GitHub.
    """
    auto = latest_release()
    manual = _manual_release()
    if auto and manual:
        if (manual["versionCode"] or 0) > (auto["versionCode"] or 0):
            return manual
        return auto
    return auto or manual


def as_row(release):
    """The selected release in the shape the page renders (one shape, one place)."""
    from types import SimpleNamespace

    if release is None:
        return None
    return SimpleNamespace(
        version=release["versionName"],
        version_code=release["versionCode"],
        download_url=release["downloadUrl"],
        notes=release["notes"],
        mandatory=bool(release["mandatory"]),
        sha256=release["sha256"],
        size_bytes=release["sizeBytes"],
        published_at=release["publishedAt"],
        source=release["source"],
    )


def clear_cache():
    """For tests, and for the page's refresh button."""
    _cache.update({"at": 0.0, "value": None, "ok": False, "error": None})
