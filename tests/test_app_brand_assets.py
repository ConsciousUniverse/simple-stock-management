"""The app wears the company's mark, not a placeholder.

The operator's first request was that the icon be the Orascom logo the web app
shows. A build can succeed with any image in `mipmap-*/`, so nothing but a test
notices when the artwork is swapped back — these assertions read the pixels.
"""

from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android/app/src/main/res"
LOGO = ROOT / "stock_manager/static/img/company-logo.png"

DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}

#: The wordmark's blue, measured from the logo itself.
BRAND_BLUE = (0, 61, 125)


def _close(pixel, target, tolerance=26):
    return all(abs(a - b) <= tolerance for a, b in zip(pixel[:3], target))


class TestTheLauncherIcon:
    @pytest.mark.parametrize("density,factor", DENSITIES.items())
    def test_it_is_the_brand_mark_at_every_density(self, density, factor):
        icon = Image.open(RES / f"mipmap-{density}/ic_launcher.png").convert("RGBA")
        expected = round(48 * factor)
        assert icon.size == (expected, expected)

        pixels = icon.load()
        blue = sum(
            1
            for x in range(icon.size[0])
            for y in range(icon.size[1])
            if pixels[x, y][3] > 200 and _close(pixels[x, y], BRAND_BLUE)
        )
        # The emblem's "M" is the brand blue; the placeholder bird had none.
        assert blue > icon.size[0] * icon.size[1] * 0.05

    @pytest.mark.parametrize("density,factor", DENSITIES.items())
    def test_the_adaptive_foreground_draws_ink_inside_the_safe_zone(
        self, density, factor
    ):
        layer = Image.open(
            RES / f"drawable-{density}/ic_launcher_foreground.png"
        ).convert("RGBA")
        size = round(108 * factor)
        assert layer.size == (size, size)

        pixels = layer.load()
        painted = sum(
            1
            for x in range(size)
            for y in range(size)
            if pixels[x, y][3] > 40
        )
        assert painted > 0
        # The launcher crops the outer ring; the mark must live inside it.
        edge = 0
        for x in range(size):
            edge += layer.getpixel((x, 0))[3] + layer.getpixel((x, size - 1))[3]
            edge += layer.getpixel((0, x))[3] + layer.getpixel((size - 1, x))[3]
        assert edge == 0

    def test_the_tile_behind_it_is_white(self):
        values = (RES / "values/ic_launcher_background.xml").read_text(encoding="utf-8")
        assert "#FFFFFFFF" in values.upper()


class TestTheSignInLogo:
    @pytest.mark.parametrize("density", DENSITIES)
    def test_it_is_the_wide_wordmark(self, density):
        logo = Image.open(RES / f"drawable-{density}/app_logo.png")
        # The wordmark is 4.6:1; the placeholder it replaced was a square.
        assert logo.size[0] / logo.size[1] > 4

    def test_the_screen_gives_it_the_width_to_be_read(self):
        layout = (RES / "layout/activity_login.xml").read_text(encoding="utf-8")
        assert 'android:adjustViewBounds="true"' in layout
        assert 'android:layout_width="96dp"' not in layout


class TestTheGenerator:
    def test_it_draws_from_the_web_app_logo(self):
        script = (ROOT / "scripts/make_app_icons.py").read_text(encoding="utf-8")
        # One source of truth: the file the web app shows in its shell bar.
        assert "stock_manager/static/img/company-logo.png" in script
        assert LOGO.exists()
