from decimal import Decimal

import pytest

from stock_manager.models import Item, ShopItem
from stock_manager.utils import SpreadsheetTools, sanitize_price

pytestmark = pytest.mark.django_db


class TestSanitizePrice:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("9.99", Decimal("9.99")),
            ("£12.30", Decimal("12.30")),
            ("12,345.6", Decimal("12345.60")),
            ("  7 ", Decimal("7.00")),
            (10, Decimal("10.00")),
            (10.555, Decimal("10.56")),  # HALF_UP rounding
            (Decimal("0E-2"), Decimal("0.00")),
            (" 3.50", Decimal("3.50")),  # non-breaking space stripped
        ],
    )
    def test_valid_values(self, value, expected):
        assert sanitize_price(value) == expected

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_values_fall_back_to_default(self, empty):
        assert sanitize_price(empty) == Decimal("0.00")

    def test_custom_default(self):
        assert sanitize_price(None, default="1.50") == Decimal("1.50")

    @pytest.mark.parametrize("bad", ["abc", "1.2.3", "NaN", "Infinity", float("nan")])
    def test_invalid_values_raise(self, bad):
        with pytest.raises(ValueError):
            sanitize_price(bad)


@pytest.fixture
def tools(rf, manager):
    request = rf.get("/")
    request.user = manager
    return SpreadsheetTools(request)


class TestGetRelatedField:
    def test_follows_relation_chain(self, tools, shop_user, make_item):
        shop_item = ShopItem.objects.create(
            shop_user=shop_user, item=make_item(sku="SKU-5"), quantity=2
        )
        assert tools.get_related_field(shop_item, "shop_user__username") == "shop1"
        assert tools.get_related_field(shop_item, "item__sku") == "SKU-5"
        assert tools.get_related_field(shop_item, "quantity") == 2

    def test_returns_none_for_broken_chain(self, tools, shop_user, make_item):
        shop_item = ShopItem.objects.create(
            shop_user=shop_user, item=make_item(), quantity=2
        )
        shop_item.item = None
        assert tools.get_related_field(shop_item, "item__sku") is None


class TestFieldChanged:
    def test_same_value_not_changed(self, tools, make_item):
        item = make_item(quantity=5)
        # String value is normalised through the model field before comparing.
        assert tools.field_changed(item, "quantity", "5") is False
        assert tools.field_changed(item, "quantity", 5) is False

    def test_different_value_changed(self, tools, make_item):
        item = make_item(quantity=5)
        assert tools.field_changed(item, "quantity", 6) is True

    def test_decimal_field_normalised(self, tools, make_item):
        item = make_item(retail_price="9.99")
        assert tools.field_changed(item, "retail_price", "9.99") is False
        assert tools.field_changed(item, "retail_price", "10.00") is True

    def test_none_equivalent_to_empty_string(self, tools, shop_user, make_item):
        shop_item = ShopItem.objects.create(
            shop_user=shop_user, item=make_item(), quantity=1
        )
        shop_item.item = None
        assert tools.field_changed(shop_item, "item", "") is False


class TestCleanupOrphanedShopItems:
    def test_null_item_rows_deleted(self, tools, shop_user, make_item):
        item = make_item()
        kept = ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        orphan = ShopItem.objects.create(shop_user=shop_user, item=None, quantity=2)

        tools.cleanup_orphaned_shopitems()

        assert ShopItem.objects.filter(pk=kept.pk).exists()
        assert not ShopItem.objects.filter(pk=orphan.pk).exists()

    def test_valid_rows_untouched(self, tools, shop_user, make_item):
        ShopItem.objects.create(shop_user=shop_user, item=make_item(), quantity=1)
        tools.cleanup_orphaned_shopitems()
        assert ShopItem.objects.count() == 1
