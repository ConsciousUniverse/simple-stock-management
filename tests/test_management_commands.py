from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command, get_commands

from stock_manager.models import Item, ShopItem

pytestmark = pytest.mark.django_db

# The import_items / import_shop_items management commands are user-supplied and
# gitignored, so they are absent from a fresh clone or deployment. Skip their
# tests when the command isn't registered rather than failing.
_COMMANDS = get_commands()


def write_csv(path, header, rows):
    lines = [",".join(header)] + [",".join(str(v) for v in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")
    return str(path)


@pytest.mark.skipif(
    "import_items" not in _COMMANDS,
    reason="import_items management command not present (user-supplied, gitignored)",
)
class TestImportItems:
    HEADER = ["sku", "desc", "unit_price", "units_total"]

    def test_creates_items_from_csv(self, tmp_path):
        csv_file = write_csv(
            tmp_path / "items.csv",
            self.HEADER,
            [["SKU-1", "Widget", "9.99", "5"], ["SKU-2", "Gadget", "1.50", "0"]],
        )
        out = StringIO()

        call_command("import_items", csv_file, stdout=out)

        item = Item.objects.get(sku="SKU-1")
        assert item.description == "Widget"
        assert item.retail_price == Decimal("9.99")
        assert item.quantity == 5
        assert "SKU-1 created" in out.getvalue()
        assert Item.objects.count() == 2

    def test_updates_existing_items(self, tmp_path, make_item):
        make_item(sku="SKU-1", description="old", retail_price="1.00", quantity=1)
        csv_file = write_csv(
            tmp_path / "items.csv",
            self.HEADER,
            [["SKU-1", "new", "2.50", "9"]],
        )
        out = StringIO()

        call_command("import_items", csv_file, stdout=out)

        item = Item.objects.get(sku="SKU-1")
        assert item.description == "new"
        assert item.retail_price == Decimal("2.50")
        assert item.quantity == 9
        assert "SKU-1 updated" in out.getvalue()


@pytest.mark.skipif(
    "import_shop_items" not in _COMMANDS,
    reason="import_shop_items management command not present (user-supplied, gitignored)",
)
class TestImportShopItems:
    HEADER = ["sku", "owner_id", "units_total"]

    def test_creates_shop_items(self, tmp_path, shop_user, make_item):
        make_item(sku="SKU-1")
        csv_file = write_csv(
            tmp_path / "shop.csv",
            self.HEADER,
            [["SKU-1", shop_user.id, "4"]],
        )
        out = StringIO()

        call_command("import_shop_items", csv_file, stdout=out)

        shop_item = ShopItem.objects.get(item__sku="SKU-1")
        assert shop_item.shop_user == shop_user
        assert shop_item.quantity == 4

    def test_missing_item_reported_and_skipped(self, tmp_path, shop_user):
        csv_file = write_csv(
            tmp_path / "shop.csv",
            self.HEADER,
            [["NOPE", shop_user.id, "4"]],
        )
        out = StringIO()

        call_command("import_shop_items", csv_file, stdout=out)

        assert ShopItem.objects.count() == 0
        assert "does not exist" in out.getvalue()

    def test_missing_user_reported_and_skipped(self, tmp_path, make_item):
        make_item(sku="SKU-1")
        csv_file = write_csv(
            tmp_path / "shop.csv",
            self.HEADER,
            [["SKU-1", "99999", "4"]],
        )
        out = StringIO()

        call_command("import_shop_items", csv_file, stdout=out)

        assert ShopItem.objects.count() == 0
        assert "does not exist" in out.getvalue()
