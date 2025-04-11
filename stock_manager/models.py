from django.db import models
from django.contrib.auth.models import User
import re
from decimal import Decimal
from django.core.validators import MinValueValidator

# Override the __str__ method of the User model to return the username
User.add_to_class("__str__", lambda self: self.username)


class Admin(models.Model):
    edit_lock = models.BooleanField(default=False)

    @staticmethod
    def is_edit_locked():
        return Admin.objects.values_list("edit_lock", flat=True)[0]


class Item(models.Model):
    sku = models.CharField(primary_key=True, unique=True, editable=True, max_length=100)
    description = models.CharField(max_length=250)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(validators=[MinValueValidator(0)])
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.sku

    def save(self, *args, **kwargs):
        if not re.match(r"^\d+(\.\d{1,2})?$", str(self.retail_price)):
            raise ValueError(
                "Retail price must be a valid number with up to 2 decimal places."
            )
        self.retail_price = Decimal(self.retail_price).quantize(Decimal("1.00"))
        super().save(*args, **kwargs)


class ShopItem(models.Model):
    shop_user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )  # Relates item to a User
    item = models.ForeignKey(Item, on_delete=models.CASCADE)  # Relates ShopItem to Item
    quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "shop_user",
            "item",
        )  # Ensure unique combination of shop_user and item

    def __str__(self):
        return f"{self.shop_user.username} - {self.item.sku}"


class TransferItem(models.Model):
    shop_user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )  # Relates item to a User
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE
    )  # Relates TransferItem to Item without a default value
    quantity = models.IntegerField(default=0)
    ordered = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shop_user.username} - {self.item.sku}"