"""The newest Android build, read from the place the builds are actually kept.

The APK is not stored on this server: Render's disk is wiped on every deploy, so
a file written here disappears and the download link rots without a word. The
builds live as assets on a GitHub release, and this module reads that list — so
publishing a release IS publishing the update, with nothing to type into a page.

Two promises the code has to keep:

* **Nothing breaks when GitHub cannot be reached.** A warehouse phone asking
  "is there an update?" must get an answer even during an outage, so the manual
  ``AppRelease`` row stays as a fallback and a failed fetch is remembered for a
  short while instead of being retried by every phone.
* **A build with no number is not silently dropped.** The app decides with
  ``versionCode``; a release whose tag carries no number cannot be compared, so
  it is returned as-is (with ``versionCode`` None) and the page shows it, rather
  than pretending nothing was published.
"""

from __future__ import annotations

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

_BUILD_WORD = re.compile(r"\bbuild\s+(\d+)\b", re.IGNORECASE)
_TRAILING_NUMBER = re.compile(r"[vV](\d+)$|[-_ ](\d+)$")
_cache = {"at": 0.0, "value": None, "ok": False}


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
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, list) else []


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


def _as_release(release):
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
        "source": "github",
    }


def latest_release(force=False):
    """The newest published build with an APK, or None when none can be read."""
    now = time.time()
    age = now - _cache["at"]
    fresh_for = CACHE_SECONDS if _cache["ok"] else FAILURE_SECONDS
    if not force and _cache["at"] and age < fresh_for:
        return _cache["value"]

    try:
        raw = _fetch_releases()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        logger.warning("App releases could not be read from %s: %s", RELEASES_REPO, exc)
        _cache.update({"at": now, "value": None, "ok": False})
        return None

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

    _cache.update({"at": now, "value": value, "ok": True})
    return value


def _manual_release():
    from stock_manager.models import AppRelease

    row = AppRelease.latest()
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
    _cache.update({"at": 0.0, "value": None, "ok": False})
