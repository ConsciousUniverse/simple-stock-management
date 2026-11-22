"""Draw the Android launcher icons from the company logo the web app shows.

One source, one brand. The launcher tile is the builder emblem cut out of the
wordmark the web app already uses, in white on the wordmark's own blue; the
sign-in screen keeps the full wordmark. Re-run after the logo changes:

    ./.venv/bin/python scripts/make_app_icons.py

Coordinates are in the 790x170 wordmark: the emblem is the last "M" plus the
figure, and the grey "CONSTRUCTION" line below it is deliberately excluded.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "stock_manager/static/img/company-logo.png"
RES = ROOT / "android/app/src/main/res"

#: The emblem inside the wordmark (the "M" and the figure beside it).
EMBLEM_BOX = (559, 6, 784, 123)
#: The wordmark's blue, measured from the same file.
BRAND_BLUE = (0, 61, 125)

DENSITIES = {"mdpi": 1.0, "hdpi": 1.5, "xhdpi": 2.0, "xxhdpi": 3.0, "xxxhdpi": 4.0}
LAUNCHER_DP = 48
FOREGROUND_DP = 108


def _load():
    return Image.open(SOURCE).convert("RGBA")


def emblem(logo):
    """The emblem in its own colours, with the white paper made transparent.

    The mark is kept as the brand draws it — a blue "M" beside a grey figure.
    Recolouring it white on blue was tried first and the figure turned to mush
    at 48dp: the two tones are what makes the shape readable at that size.
    """
    crop = logo.crop(EMBLEM_BOX).convert("RGBA")
    pixels = crop.load()
    out = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    out_pixels = out.load()
    for x in range(crop.width):
        for y in range(crop.height):
            r, g, b, _ = pixels[x, y]
            if r > 240 and g > 240 and b > 240:
                out_pixels[x, y] = (0, 0, 0, 0)
            else:
                out_pixels[x, y] = (r, g, b, 255)
    return out


def wordmark(logo):
    """The full wordmark with the white paper made transparent."""
    pixels = logo.load()
    out = logo.copy()
    out_pixels = out.load()
    for x in range(logo.width):
        for y in range(logo.height):
            r, g, b, _ = pixels[x, y]
            if r > 240 and g > 240 and b > 240:
                out_pixels[x, y] = (0, 0, 0, 0)
    return out


def _fitted(mark, box_w, box_h):
    scale = min(box_w / mark.width, box_h / mark.height)
    size = (max(1, round(mark.width * scale)), max(1, round(mark.height * scale)))
    return mark.resize(size, Image.LANCZOS)


def _tile(size, mark):
    """A blue tile with rounded corners and the emblem centred in it."""
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    radius = round(size * 0.22)
    ImageDraw.Draw(tile).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=(255, 255, 255, 255)
    )
    art = _fitted(mark, round(size * 0.88), round(size * 0.70))
    tile.alpha_composite(
        art, ((size - art.width) // 2, (size - art.height) // 2)
    )
    return tile


def _foreground(size, mark):
    """The adaptive foreground: the emblem inside the 66% safe zone."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    art = _fitted(mark, round(size * 0.74), round(size * 0.56))
    layer.alpha_composite(art, ((size - art.width) // 2, (size - art.height) // 2))
    return layer


def main():
    logo = _load()
    mark = emblem(logo)
    words = wordmark(logo)

    for density, factor in DENSITIES.items():
        launcher = round(LAUNCHER_DP * factor)
        tile = _tile(launcher, mark)
        target = RES / f"mipmap-{density}"
        target.mkdir(parents=True, exist_ok=True)
        tile.save(target / "ic_launcher.png")

        foreground = _foreground(round(FOREGROUND_DP * factor), mark)
        (RES / f"drawable-{density}").mkdir(parents=True, exist_ok=True)
        foreground.save(RES / f"drawable-{density}/ic_launcher_foreground.png")

        wide = round(360 * factor)
        sign_in = words.resize((wide, round(words.height * wide / words.width)), Image.LANCZOS)
        sign_in.save(RES / f"drawable-{density}/app_logo.png")

    print("icons written from", SOURCE.name, "· emblem", mark.size, "· wordmark", words.size)


if __name__ == "__main__":
    main()
