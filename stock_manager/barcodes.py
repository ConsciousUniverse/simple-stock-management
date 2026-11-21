"""Code 128 barcodes for item labels.

The barcode carries the item identifier the company uses (the item SKU), so a
label printed here can be scanned by the site application and matched back to
the same item without a lookup table.
"""

import io

from barcode import Code128
from barcode.writer import SVGWriter

#: Code 128 handles printable ASCII only; a longer code would not fit a label.
MAX_CODE_LENGTH = 48


class BarcodeError(ValueError):
    """The value cannot be rendered as a Code 128 barcode."""


def normalise_barcode_value(value):
    code = (value or "").strip()
    if not code:
        raise BarcodeError("An item code is required to print a barcode.")
    if len(code) > MAX_CODE_LENGTH:
        raise BarcodeError(
            f"The item code is longer than {MAX_CODE_LENGTH} characters."
        )
    if not code.isascii() or not code.isprintable():
        raise BarcodeError(
            "The item code must contain printable ASCII characters only."
        )
    return code


def render_barcode_svg(value, module_height=12.0, module_width=0.24, quiet_zone=2.0):
    """Return an inline ``<svg>`` element for ``value``.

    The XML prolog and doctype are stripped so the markup can be embedded in an
    HTML page (and printed) without a second request.
    """
    code = normalise_barcode_value(value)
    buffer = io.BytesIO()
    Code128(code, writer=SVGWriter()).write(
        buffer,
        options={
            "module_height": module_height,
            "module_width": module_width,
            "quiet_zone": quiet_zone,
            "write_text": False,
            "background": "white",
            "foreground": "black",
        },
    )
    svg = buffer.getvalue().decode("utf-8")
    start = svg.find("<svg")
    end = svg.rfind("</svg>")
    if start == -1 or end == -1:
        raise BarcodeError("The barcode could not be rendered.")
    return svg[start : end + len("</svg>")]
