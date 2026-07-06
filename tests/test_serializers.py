import pytest

from stock_manager.models import ShopItem, TransferItem
from stock_manager.serializers import (
    ItemSerializer,
    ShopItemSerializer,
    TransferItemSerializer,
)

pytestmark = pytest.mark.django_db


def item_payload(**overrides):
    payload = {
        "sku": "SKU-1",
        "description": "Widget",
        "retail_price": "9.99",
        "quantity": 5,
    }
    payload.update(overrides)
    return payload


class TestItemSerializer:
    def test_valid_payload(self, db):
        serializer = ItemSerializer(data=item_payload())
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["quantity"] == 5
        assert serializer.validated_data["retail_price"] == 9.99

    def test_quantity_given_as_numeric_string_is_coerced(self, db):
        serializer = ItemSerializer(data=item_payload(quantity="12"))
        assert serializer.is_valid(), serializer.errors
        assert serializer.validated_data["quantity"] == 12

    @pytest.mark.parametrize("bad_quantity", ["abc", "-1", "1.5", ""])
    def test_invalid_quantity_rejected(self, db, bad_quantity):
        serializer = ItemSerializer(data=item_payload(quantity=bad_quantity))
        assert not serializer.is_valid()
        assert "quantity" in serializer.errors

    @pytest.mark.parametrize("bad_price", ["abc", "-1.00", "10.999", ""])
    def test_invalid_price_rejected(self, db, bad_price):
        serializer = ItemSerializer(data=item_payload(retail_price=bad_price))
        assert not serializer.is_valid()
        assert "retail_price" in serializer.errors

    @pytest.mark.parametrize("good_price", ["0", "10", "10.5", "10.55"])
    def test_valid_price_formats_accepted(self, db, good_price):
        serializer = ItemSerializer(data=item_payload(retail_price=good_price))
        assert serializer.is_valid(), serializer.errors

    def test_serializes_expected_fields(self, make_item):
        data = ItemSerializer(make_item()).data
        assert set(data.keys()) == {"sku", "description", "retail_price", "quantity"}


class TestShopItemSerializer:
    def test_item_fields_present_when_item_exists(self, shop_user, make_item):
        item = make_item(sku="SKU-2", description="Gadget")
        shop_item = ShopItem.objects.create(shop_user=shop_user, item=item, quantity=3)
        data = ShopItemSerializer(shop_item).data
        assert data["item_sku"] == "SKU-2"
        assert data["item_description"] == "Gadget"
        assert data["item_is_active"] is True
        assert data["quantity"] == 3
        assert data["shop_user"]["username"] == "shop1"

    def test_item_fields_none_when_item_deleted(self, shop_user, make_item):
        item = make_item()
        shop_item = ShopItem.objects.create(shop_user=shop_user, item=item, quantity=3)
        item.delete()
        shop_item.refresh_from_db()
        data = ShopItemSerializer(shop_item).data
        assert data["item"] is None
        assert data["item_sku"] is None
        assert data["item_description"] is None
        assert data["item_is_active"] is False

    def test_inactive_item_flagged(self, shop_user, make_item):
        item = make_item(is_active=False)
        shop_item = ShopItem.objects.create(shop_user=shop_user, item=item, quantity=3)
        data = ShopItemSerializer(shop_item).data
        assert data["item_is_active"] is False


class TestTransferItemSerializer:
    def test_nested_output(self, shop_user, make_item):
        item = make_item(sku="SKU-3")
        transfer = TransferItem.objects.create(
            shop_user=shop_user, item=item, quantity=4, ordered=True
        )
        data = TransferItemSerializer(transfer).data
        assert data["item"]["sku"] == "SKU-3"
        assert data["shop_user"]["username"] == "shop1"
        assert data["quantity"] == 4
        assert data["ordered"] is True
