import os, subprocess, sys

if os.path.exists("db.sqlite3"):
    os.remove("db.sqlite3")
subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], check=True)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ssm.settings")
import django
django.setup()
from django.contrib.auth.models import Group, User
from stock_manager.models import Admin, Item

for g in ("managers", "shop_users", "receive_mail"):
    Group.objects.get_or_create(name=g)
Admin.objects.get_or_create(id=1)

def mk(name, group):
    u, _ = User.objects.get_or_create(username=name, defaults={"email": f"{name}@example.com"})
    u.set_password("test-pass-123")
    u.save()
    u.groups.add(Group.objects.get(name=group))

mk("manager", "managers")
mk("shop1", "shop_users")
mk("shop2", "shop_users")
for sku, desc, price, qty in [("KB-001", "Keyboard", "25.00", 10),
                              ("MS-001", "Mouse", "12.50", 5),
                              ("MN-001", "Monitor", "150.00", 0)]:
    Item.objects.update_or_create(sku=sku, defaults=dict(description=desc, retail_price=price, quantity=qty))
print("Seed complete: users manager/shop1/shop2, password test-pass-123, 3 items.")