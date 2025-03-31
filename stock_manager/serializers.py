from rest_framework import serializers
from .models import Item, ShopItem, TransferItem
from django.contrib.auth.models import User, Group
import re

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "groups"]

class ItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Item
        fields = ["sku", "description", "retail_price", "quantity"]

    def validate_retail_price(self, value):
        if not re.match(r'^\d+(\.\d{1,2})?$', str(value)):
            raise serializers.ValidationError("Retail price must be a valid price (2 decimal places max).")
        return value

class ShopItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer()
    shop_user = UserSerializer()

    class Meta:
        model = ShopItem
        fields = ["shop_user", "item", "quantity", "last_updated"]

class TransferItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer()
    shop_user = UserSerializer()

    class Meta:
        model = TransferItem
        fields = ["shop_user", "item", "quantity", "ordered", "last_updated"]
