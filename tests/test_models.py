from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from stock_manager.models import Admin, Item, ShopItem, TransferItem

pytestmark = pytest.mark.django_db


class TestAdminModel:
    def test_defaults(self, app_config):
        assert app_config.edit_lock is False
        assert app_config.allow_uploads is False
        assert app_config.allow_upload_deletions is False
        assert app_config.allow_email_notifications is False
        assert app_config.records_per_page == 25

    def test_static_accessors_reflect_saved_values(self, app_config):
        app_config.edit_lock = True
        app_config.allow_uploads = True
        app_config.allow_upload_deletions = True
        app_config.allow_email_notifications = True
        app_config.records_per_page = 7
        app_config.save()

        assert Admin.is_edit_locked() is True
        assert Admin.is_allow_updoads() is True
        assert Admin.is_allow_upload_deletions() is True
        assert Admin.is_allow_email_notifications() is True
        assert Admin.get_records_per_page() == 7

    def test_str(self, app_config):
        assert str(app_config) == "Configuration Options"

    def test_static_accessors_safe_without_config_row(self, db):
        # A fresh install has no Admin row; accessors must return defaults.
        assert Admin.is_edit_locked() is False
        assert Admin.is_allow_updoads() is False
        assert Admin.is_allow_upload_deletions() is False
        assert Admin.is_allow_email_notifications() is False
        assert Admin.get_records_per_page() == 25


class TestItemModel:
    def test_create_stores_two_decimal_places(self, make_item):
        item = make_item(retail_price="9.99")
        item.refresh_from_db()
        assert item.retail_price == Decimal("9.99")

    def test_price_is_rounded_half_up(self, make_item):
        assert make_item(sku="A", retail_price="10.555").retail_price == Decimal("10.56")
        assert make_item(sku="B", retail_price="10.554").retail_price == Decimal("10.55")

    def test_price_accepts_scientific_notation_decimal(self, make_item):
        # Decimal('0E-2') is how a zero produced by arithmetic can look.
        item = make_item(retail_price=Decimal("0E-2"))
        assert item.retail_price == Decimal("0.00")

    def test_invalid_price_raises_value_error(self, db):
        with pytest.raises(ValueError):
            Item.objects.create(
                sku="BAD", description="x", retail_price="not-a-price", quantity=1
            )

    def test_negative_price_raises_value_error(self, db):
        with pytest.raises(ValueError):
            Item.objects.create(
                sku="NEG", description="x", retail_price="-5.00", quantity=1
            )

    def test_none_price_raises_value_error(self, db):
        with pytest.raises(ValueError):
            Item.objects.create(
                sku="NONE", description="x", retail_price=None, quantity=1
            )

    def test_negative_quantity_fails_validation(self, make_item):
        item = make_item(quantity=0)
        item.quantity = -1
        with pytest.raises(ValidationError):
            item.full_clean()

    def test_str_reflects_active_state(self, make_item):
        active = make_item(sku="ACT")
        inactive = make_item(sku="INACT", is_active=False)
        assert str(active) == "ACT (Active)"
        assert str(inactive) == "INACT (Inactive)"


class TestShopItemModel:
    def test_unique_together_shop_user_item(self, shop_user, make_item):
        item = make_item()
        ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        with pytest.raises(IntegrityError):
            ShopItem.objects.create(shop_user=shop_user, item=item, quantity=2)

    def test_item_set_null_on_item_delete(self, shop_user, make_item):
        item = make_item()
        shop_item = ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        item.delete()
        shop_item.refresh_from_db()
        assert shop_item.item is None

    def test_str_with_and_without_item(self, shop_user, make_item):
        item = make_item(sku="SKU-9")
        shop_item = ShopItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        assert str(shop_item) == "shop1 - SKU-9"
        item.delete()
        shop_item.refresh_from_db()
        assert str(shop_item) == "shop1 - Item Deleted"


class TestTransferItemModel:
    def test_defaults_and_str(self, shop_user, make_item):
        item = make_item(sku="SKU-7")
        transfer = TransferItem.objects.create(shop_user=shop_user, item=item)
        assert transfer.quantity == 0
        assert transfer.ordered is False
        assert transfer.created_at is not None
        assert str(transfer) == "shop1 - SKU-7"

    def test_cascade_deleted_with_item(self, shop_user, make_item):
        item = make_item()
        TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        item.delete()
        assert TransferItem.objects.count() == 0

    def test_cascade_deleted_with_user(self, shop_user, make_item):
        item = make_item()
        TransferItem.objects.create(shop_user=shop_user, item=item, quantity=1)
        shop_user.delete()
        assert TransferItem.objects.count() == 0
