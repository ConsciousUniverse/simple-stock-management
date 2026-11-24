"""Item barcodes: rendering, the SVG endpoint and the printable label sheet."""

import pytest

from stock_manager.barcodes import (
    MAX_CODE_LENGTH,
    BarcodeError,
    barcode_value,
    normalise_barcode_value,
    render_barcode_svg,
)
from stock_manager import item_codes

pytestmark = pytest.mark.django_db


class TestBarcodeRendering:
    def test_renders_an_inline_svg_with_bars(self):
        svg = render_barcode_svg("NSCOM-1001")

        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        # The XML prolog would break the markup when embedded in a page.
        assert "<?xml" not in svg
        assert "<!DOCTYPE" not in svg
        assert svg.count("<rect") > 20

    def test_two_codes_produce_different_bars(self):
        assert render_barcode_svg("NSCOM-1001") != render_barcode_svg("NSCOM-1002")

    def test_accepts_an_ordinary_company_code(self):
        assert normalise_barcode_value("  P26E11407 ") == "P26E11407"

    @pytest.mark.parametrize("value", ["", "   ", None])
    def test_rejects_an_empty_code(self, value):
        with pytest.raises(BarcodeError):
            normalise_barcode_value(value)

    def test_rejects_non_ascii_because_code128_cannot_encode_it(self):
        with pytest.raises(BarcodeError):
            render_barcode_svg("كابل 3×6")

    def test_rejects_a_code_longer_than_a_label_can_hold(self):
        with pytest.raises(BarcodeError):
            normalise_barcode_value("A" * (MAX_CODE_LENGTH + 1))


class TestBarcodeEndpoint:
    def test_returns_an_svg_document(self, manager_client, make_item):
        make_item(sku="NSCOM-1001")

        response = manager_client.get("/api/items/NSCOM-1001/barcode.svg")

        assert response.status_code == 200
        assert response["Content-Type"] == "image/svg+xml"
        assert response.content.decode().startswith("<svg")

    def test_requires_authentication(self, api_client, make_item):
        make_item(sku="NSCOM-1001")

        response = api_client.get("/api/items/NSCOM-1001/barcode.svg")

        assert response.status_code in (401, 403)

    def test_an_unencodable_code_is_a_client_error(self, manager_client):
        response = manager_client.get("/api/items/كابل/barcode.svg")

        assert response.status_code == 400

    def test_two_oracle_codes_of_one_item_answer_with_one_barcode(
        self, manager_client, make_item
    ):
        first = make_item(sku="ORACLE-A", quantity=5)
        second = make_item(sku="ORACLE-B", quantity=7)
        group = item_codes.merge_codes([first.sku, second.sku])

        one = manager_client.get(f"/api/items/{first.sku}/barcode.svg").content.decode()
        two = manager_client.get(f"/api/items/{second.sku}/barcode.svg").content.decode()

        assert one == two
        assert one == render_barcode_svg(group.code)


class TestLabelSheet:
    def test_barcode_value_prefers_the_internal_code(self, make_item):
        first = make_item(sku="ORACLE-A")
        second = make_item(sku="ORACLE-B")
        group = item_codes.merge_codes([first.sku, second.sku])
        first.refresh_from_db()

        assert barcode_value(first) == group.code

    def test_the_label_barcode_covers_every_oracle_code_of_the_item(
        self, client, manager, make_item
    ):
        first = make_item(sku="ORACLE-A", description="Nail 3in", quantity=5)
        second = make_item(sku="ORACLE-B", description="Nail 3in", quantity=7)
        group = item_codes.merge_codes([first.sku, second.sku])
        client.force_login(manager)

        html = client.get(f"/labels/?skus={first.sku}").content.decode()

        assert html.count('class="label"') == 1
        assert group.code in html
        assert first.sku in html
        assert second.sku in html
        assert render_barcode_svg(group.code) in html
        assert render_barcode_svg(first.sku) not in html

    def test_prints_one_label_per_item_and_copy(self, client, manager, make_item):
        make_item(sku="NSCOM-1001", description="Circuit breaker")
        make_item(sku="NSCOM-1002", description="Cable tray")
        client.force_login(manager)

        html = client.get("/labels/?skus=NSCOM-1001,NSCOM-1002&copies=2").content.decode()

        assert html.count('class="label"') == 4
        assert "NSCOM-1001" in html
        assert "Circuit breaker" in html
        assert html.count("<svg") == 4

    def test_an_unknown_code_is_reported_not_silently_skipped(self, client, manager, make_item):
        make_item(sku="NSCOM-1001")
        client.force_login(manager)

        html = client.get("/labels/?skus=NSCOM-1001,MISSING-1").content.decode()

        assert html.count('class="label"') == 1
        assert "MISSING-1" in html

    def test_requires_a_login(self, client):
        response = client.get("/labels/?skus=NSCOM-1001")

        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]
