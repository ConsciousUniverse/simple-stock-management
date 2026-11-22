"""What the phone build itself must and must not contain.

The screens are Android resources, so no Python test can render them — but the
two promises the operator asked for are readable as text, and they are the kind
that a later "helpful" edit silently undoes: the server address must not be
typeable, and the launcher icon must be the company mark.
"""

import re
from pathlib import Path

ANDROID = Path(__file__).resolve().parent.parent / "android"
RES = ANDROID / "app" / "src" / "main" / "res"
JAVA = ANDROID / "app" / "src" / "main" / "java" / "com" / "cortoba" / "warehouse"


class TestTheServerAddressCannotBeTyped:
    def test_the_sign_in_screen_has_no_address_field(self):
        layout = (RES / "layout" / "activity_login.xml").read_text(encoding="utf-8")

        assert "serverInput" not in layout
        assert "textUri" not in layout

    def test_no_screen_offers_to_change_it(self):
        for path in RES.glob("layout/*.xml"):
            text = path.read_text(encoding="utf-8")
            assert "server_label" not in text, path.name

    def test_the_session_reads_the_address_from_the_build(self):
        source = (JAVA / "Session.kt").read_text(encoding="utf-8")

        assert "val baseUrl: String = BuildConfig.DEFAULT_BASE_URL" in source
        # No setter and no stored copy: an old value cannot outlive the build.
        assert 'prefs.getString("base_url"' not in source
        assert "var baseUrl" not in source


class TestTheIconIsTheCompanyMark:
    def test_the_launcher_icon_exists_at_every_density(self):
        for density in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
            icon = RES / f"mipmap-{density}" / "ic_launcher.png"
            assert icon.exists(), icon
            assert icon.stat().st_size > 1000, icon

    def test_newer_android_gets_an_adaptive_icon_of_the_same_mark(self):
        adaptive = (RES / "mipmap-anydpi-v26" / "ic_launcher.xml").read_text(
            encoding="utf-8"
        )

        assert "@drawable/ic_launcher_foreground" in adaptive
        assert "@drawable/ic_launcher_background" in adaptive
        for density in ("mdpi", "xxxhdpi"):
            assert (RES / f"drawable-{density}" / "ic_launcher_foreground.png").exists()

    def test_the_sign_in_screen_shows_it(self):
        layout = (RES / "layout" / "activity_login.xml").read_text(encoding="utf-8")

        assert 'android:src="@drawable/app_logo"' in layout
        assert (RES / "drawable-xxxhdpi" / "app_logo.png").exists()


class TestTheBuildNumberGrows:
    def test_the_version_code_is_above_the_published_build(self):
        gradle = (ANDROID / "app" / "build.gradle.kts").read_text(encoding="utf-8")

        code = int(re.search(r"versionCode\s*=\s*(\d+)", gradle).group(1))
        # Build 1 is the published one; a build that does not grow is never
        # offered to a phone that already has it.
        assert code >= 2
