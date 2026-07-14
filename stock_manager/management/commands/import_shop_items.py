import csv
from django.core.management.base import BaseCommand
from stock_manager.models import Item, ShopItem
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = "Import items from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="The path to the CSV file")

    def handle(self, *args, **kwargs):
        csv_file = kwargs["csv_file"]
        with open(csv_file, newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:

                # item, created = Item.objects.update_or_create(
                #     sku=row['sku'],
                #     defaults={
                #         'description': row['description'],
                #         'retail_price': row['retail_price'],
                #         'quantity': row['quantity'],
                #     }
                # )


                # Ensure the item exists
                try:
                    item = Item.objects.get(sku=row["sku"])
                except Item.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"Item with SKU {row['sku']} does not exist"))
                    continue

                # Ensure the shop_user_id exists
                if not User.objects.filter(id=row["owner_id"]).exists():
                    self.stdout.write(self.style.ERROR(f"ShopUser with id {row['owner_id']} does not exist"))
                    continue

                shop_item, created = ShopItem.objects.update_or_create(
                    item=item,
                    defaults={
                        "quantity": row["units_total"],
                        "shop_user_id": row["owner_id"],
                    },
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Item {item.sku} created"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Item {item.sku} updated"))
