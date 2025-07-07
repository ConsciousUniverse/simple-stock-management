from rest_framework import serializers
from .models import Item, ShopItem, TransferItem
from django.contrib.auth.models import User
import re


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "groups"]


class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ["sku", "description", "retail_price", "quantity"]

    def validate_quantity(self, value):
        if not re.match(r"^\d+$", str(value)):
            raise serializers.ValidationError("Quantity must be a valid integer.")
        return int(value)

    def validate_retail_price(self, value):
        if not re.match(r"^\d+(\.\d{1,2})?$", str(value)):
            raise serializers.ValidationError(
                "Retail price must be a valid price (2 decimal places max)."
            )
        return float(value)


class ShopItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(required=False, allow_null=True)
    shop_user = UserSerializer()
    item_is_active = serializers.SerializerMethodField()
    item_description = serializers.SerializerMethodField()
    item_sku = serializers.SerializerMethodField()

    class Meta:
        model = ShopItem
        fields = ["shop_user", "item", "quantity", "last_updated", "item_is_active", "item_description", "item_sku"]

    def get_item_is_active(self, obj):
        if obj.item:
            return getattr(obj.item, 'is_active', False)
        return False

    def get_item_description(self, obj):
        if obj.item:
            return getattr(obj.item, 'description', None)
        return None

    def get_item_sku(self, obj):
        if obj.item:
            return getattr(obj.item, 'sku', None)
        return None


class TransferItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer()
    shop_user = UserSerializer()

    class Meta:
        model = TransferItem
        fields = ["shop_user", "item", "quantity", "ordered", "last_updated"]
