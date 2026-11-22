"""Build the release APK and publish it, so every phone is offered it.

Publishing the build IS shipping the update: the app reads the newest release
from the repository named in ``APP_RELEASES_REPO``, so no link is distributed
and no APK is sent to anyone.

    GITHUB_TOKEN=ghp_… python scripts/publish_app.py --notes "…"

The build number comes from ``android/app/build.gradle.kts`` and is the tag
(``v3``), which is what the phones compare. Bump it before running: a build
whose number has not grown is never offered, so this script refuses it rather
than publishing something no phone will take.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRADLE = ROOT / "android/app/build.gradle.kts"
APK = ROOT / "android/app/build/outputs/apk/release/app-release.apk"

RELEASES_REPO = os.environ.get("APP_RELEASES_REPO", "melsofany/warehouse-app-releases")
API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"


def _request(url, *, token, method="GET", body=None, content_type="application/json"):
    request = urllib.request.Request(url, method=method, data=body)
    request.add_header("Authorization", f"token {token}")
    request.add_header("Accept", "application/vnd.github+json")
    if body is not None:
        request.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"{method} {url} -> {exc.code}: {detail[:400]}") from exc


def read_version():
    """The number the phones compare, and the name people read."""
    text = GRADLE.read_text(encoding="utf-8")
    code = re.search(r"versionCode\s*=\s*(\d+)", text)
    name = re.search(r'versionName\s*=\s*"([^"]+)"', text)
    if not code or not name:
        raise SystemExit("versionCode / versionName not found in build.gradle.kts")
    return int(code.group(1)), name.group(1)


def build():
    env = dict(os.environ)
    env.setdefault("JAVA_HOME", "/workspace/tools/jdk")
    env.setdefault("ANDROID_HOME", "/workspace/tools/android-sdk")
    env["PATH"] = f"{env['JAVA_HOME']}/bin:{env['PATH']}"
    gradle = os.environ.get("GRADLE_BIN", "/workspace/tools/gradle-8.7/bin/gradle")
    if not Path(gradle).exists():
        gradle = "gradle"
    subprocess.run(
        [gradle, ":app:assembleRelease", "--console=plain"],
        cwd=ROOT / "android",
        env=env,
        check=True,
    )


def release_exists(tag, token):
    try:
        _request(f"{API}/repos/{RELEASES_REPO}/releases/tags/{tag}", token=token)
        return True
    except SystemExit as exc:
        if "-> 404" in str(exc):
            return False
        raise


def publish(tag, name, notes, token):
    payload = json.dumps(
        {"tag_name": tag, "name": name, "body": notes, "draft": False, "prerelease": False}
    ).encode()
    release = _request(
        f"{API}/repos/{RELEASES_REPO}/releases", token=token, method="POST", body=payload
    )
    data = APK.read_bytes()
    asset = _request(
        f"{UPLOADS}/repos/{RELEASES_REPO}/releases/{release['id']}/assets"
        f"?name=warehouse-{tag.lstrip('v')}.apk",
        token=token,
        method="POST",
        body=data,
        content_type="application/vnd.android.package-archive",
    )
    return release, asset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", default="", help="release notes shown in the app")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required to publish the release")

    code, name = read_version()
    tag = f"v{code}"
    if release_exists(tag, token):
        raise SystemExit(
            f"{tag} is already published: bump versionCode in "
            "android/app/build.gradle.kts, or the phones would never see the change"
        )

    if not args.skip_build:
        build()
    if not APK.exists():
        raise SystemExit(f"no APK at {APK}")

    data = APK.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    notes = args.notes.strip()
    notes = (notes + "\n\n" if notes else "") + f"SHA-256: {digest}\nSize: {len(data)} bytes"

    release, asset = publish(tag, f"Warehouse {name} (build {code})", notes, token)
    print(f"published {tag}: {release['html_url']}")
    print(f"asset: {asset['browser_download_url']} ({len(data)} bytes)")
    print(f"sha256: {digest}")


if __name__ == "__main__":
    sys.exit(main())
