"""An internal code for every item, and one code over several Oracle codes.

The live database predates the migration directory, so the table and column are
created only where they are missing (``_adopt.ensure_models``); the recorded
state still describes exactly what the models describe. Every existing item is
then given its own internal code (00001, 00002, ...), which is a 1:1 adoption:
no quantity, document or Oracle code changes. Merging the codes that name the
same article is a decision the warehouse makes afterwards on /items/groups/.
"""

import django.db.models.deletion
from django.db import migrations, models

from ._adopt import ensure_models


def assign_groups(apps, schema_editor):
    """Give every item that has no internal code one of its own.

    Idempotent: an item that already carries a code is left alone, so a
    re-run (or a partially applied deploy) cannot create a second one.
    """
    Item = apps.get_model("stock_manager", "Item")
    ItemGroup = apps.get_model("stock_manager", "ItemGroup")

    pending = Item.objects.filter(internal_group__isnull=True).order_by("sku")
    if not pending.exists():
        return

    existing = [
        int(code)
        for code in ItemGroup.objects.values_list("code", flat=True)
        if str(code).isdigit()
    ]
    number = max(existing, default=0)
    for item in pending:
        number += 1
        group = ItemGroup.objects.create(code=f"{number:05d}")
        item.internal_group = group
        item.save(update_fields=["internal_group"])


class Migration(migrations.Migration):

    dependencies = [
        ("stock_manager", "0011_alter_auditevent_action"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="ItemGroup",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("code", models.CharField(blank=True, max_length=20, unique=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                    ],
                    options={
                        "verbose_name": "Internal item code",
                        "verbose_name_plural": "Internal item codes",
                        "ordering": ("code",),
                    },
                ),
                migrations.AddField(
                    model_name="item",
                    name="internal_group",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="items",
                        to="stock_manager.itemgroup",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    lambda apps, schema_editor: ensure_models(
                        schema_editor, ("ItemGroup", "Item")
                    ),
                    migrations.RunPython.noop,
                )
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="auditevent",
                    name="action",
                    field=models.CharField(
                        choices=[
                            ("login", "Signed in"),
                            ("login_failed", "Sign-in refused"),
                            ("logout", "Signed out"),
                            ("password_changed", "Password changed"),
                            ("document_created", "Document created"),
                            ("document_approved", "Document approved"),
                            ("document_rejected", "Document rejected"),
                            ("document_permit", "Company voucher recorded"),
                            ("item_created", "Item created"),
                            ("item_updated", "Item changed"),
                            ("item_deleted", "Item deleted"),
                            ("item_grouped", "Oracle codes grouped under an internal code"),
                            ("item_ungrouped", "Oracle code moved to another internal code"),
                            ("transfer_sent", "Transfer requested"),
                            ("transfer_completed", "Transfer dispatched"),
                            ("data_imported", "Spreadsheet imported"),
                            ("data_exported", "Spreadsheet exported"),
                            ("user_created", "User created"),
                            ("user_updated", "User changed"),
                            ("user_deactivated", "User deactivated"),
                            ("settings_changed", "Settings changed"),
                            ("release_published", "App release published"),
                            ("user_unlocked", "Lockout cleared"),
                            ("user_reset", "Password reset on deploy"),
                            ("phone_changed", "Sign-in phone changed"),
                            ("phone_requested", "Phone change requested"),
                            ("phone_request_decided", "Phone change decided"),
                            ("mobile_device_cleared", "Phone unbound from the app"),
                        ],
                        max_length=32,
                    ),
                )
            ],
            database_operations=[],
        ),
        migrations.RunPython(assign_groups, migrations.RunPython.noop),
    ]
