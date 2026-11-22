"""One phone per account.

An account signed in on two phones is two people moving stock in one name, and
the audit trail cannot tell them apart. The app keeps a device id; the first
phone that signs in claims the account, and a second one is refused by name
until a warehouse manager clears the first from «مستخدمو التطبيق».
"""

from django.db import migrations, models

from ._adopt import ensure_models


class Migration(migrations.Migration):

    dependencies = [("stock_manager", "0009_document_voucher_fields")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="mobileprofile",
                    name="device_id",
                    field=models.CharField(blank=True, default="", max_length=64),
                ),
                migrations.AddField(
                    model_name="mobileprofile",
                    name="device_label",
                    field=models.CharField(blank=True, default="", max_length=120),
                ),
                migrations.AddField(
                    model_name="mobileprofile",
                    name="device_bound_at",
                    field=models.DateTimeField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name="mobilesession",
                    name="device_id",
                    field=models.CharField(blank=True, default="", max_length=64),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    lambda apps, schema_editor: ensure_models(
                        schema_editor, ("MobileProfile", "MobileSession")
                    ),
                    migrations.RunPython.noop,
                )
            ],
        )
    ]
