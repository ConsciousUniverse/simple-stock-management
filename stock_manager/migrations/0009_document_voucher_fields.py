"""The signed voucher that arrives with a document from site.

A site user photographs the paper and writes what is on it: the date on the
voucher, where the goods go, and the engineer who signed it. Without these the
warehouse manager approves a list of quantities with no way to check it against
the paper behind it.

The photo is stored in the database, not on disk: Render wipes the disk on
every deploy, so a file under MEDIA_ROOT would be a broken image within a week.
"""

from django.db import migrations, models

from ._adopt import ensure_models


class Migration(migrations.Migration):

    dependencies = [("stock_manager", "0008_release_source")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="stockdocument",
                    name="document_date",
                    field=models.DateField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name="stockdocument",
                    name="location",
                    field=models.CharField(blank=True, default="", max_length=200),
                ),
                migrations.AddField(
                    model_name="stockdocument",
                    name="engineer_name",
                    field=models.CharField(blank=True, default="", max_length=120),
                ),
                migrations.AddField(
                    model_name="stockdocument",
                    name="photo",
                    field=models.BinaryField(blank=True, editable=False, null=True),
                ),
                migrations.AddField(
                    model_name="stockdocument",
                    name="photo_type",
                    field=models.CharField(blank=True, default="", max_length=60),
                ),
                migrations.AddField(
                    model_name="stockdocument",
                    name="photo_name",
                    field=models.CharField(blank=True, default="", max_length=120),
                ),
                migrations.AddField(
                    model_name="stockdocument",
                    name="photo_uploaded_at",
                    field=models.DateTimeField(null=True, blank=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    lambda apps, schema_editor: ensure_models(
                        schema_editor, ("StockDocument",)
                    ),
                    migrations.RunPython.noop,
                )
            ],
        )
    ]
