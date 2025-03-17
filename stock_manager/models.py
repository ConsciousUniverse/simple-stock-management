from django.db import models
from django.contrib.auth.models import User
import re
from decimal import Decimal

class Admin(models.Model):
    edit_lock = models.BooleanField(default=False)

class Item(models.Model):
    sku = models.CharField(primary_key=True, unique=True, editable=True, max_length=100)
    description = models.CharField(max_length=250)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField()
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.sku

    def save(self, *args, **kwargs):
        if not re.match(r'^\d+(\.\d{1,2})?$', str(self.retail_price)):
            raise ValueError("Retail price must be a valid number with up to 2 decimal places.")
        self.retail_price = Decimal(self.retail_price).quantize(Decimal('1.00'))
        super().save(*args, **kwargs)

    def transfer_to_shop(self, shop_user, transfer_quantity):
        if Admin.objects.first().edit_lock:
            raise ValueError("Transfers are disabled in update mode.")
        if self.quantity < transfer_quantity:
            raise ValueError("Not enough stock to transfer")

        self.quantity -= transfer_quantity
        self.save()

        shop_item, created = ShopItem.objects.get_or_create(
            item=self,
            shop_user=shop_user,
            defaults={
                'last_updated': self.last_updated,
            }
        )

        shop_item.quantity += transfer_quantity
        shop_item.save()


class ShopItem(models.Model):
    id = models.AutoField(primary_key=True)  # Add primary key field
    shop_user = models.ForeignKey(User, on_delete=models.CASCADE)  # Relates item to a User
    item = models.ForeignKey(Item, on_delete=models.CASCADE, default=1)  # Relates ShopItem to Item with a default value
    quantity = models.IntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.shop_user.username} - {self.item.sku}"
