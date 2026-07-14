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
                item, created = Item.objects.update_or_create(
                    sku=row["sku"],
                    defaults={
                        "description": row["desc"],
                        "retail_price": row["unit_price"],
                        "quantity": row["units_total"],
                    },
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Item {item.sku} created"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Item {item.sku} updated"))
