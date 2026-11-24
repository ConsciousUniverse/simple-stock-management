"""Item card fields: the project printed on every card, and each item's sub
inventory and Arabic name.

The live database may lack these columns (see ``_adopt``), so the database work
adopts the schema — it adds only the columns that are missing — while the
recorded state stays exact. Existing rows keep their data; the new text columns
start empty and are filled from the App Configuration page and the item admin.
"""

from django.db import migrations, models

from ._adopt import ensure_models


class Migration(migrations.Migration):

    dependencies = [
        ("stock_manager", "0012_itemgroup_alter_auditevent_action_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="admin",
                    name="project_name",
                    field=models.CharField(blank=True, db_default="", default="", max_length=120),
                ),
                migrations.AddField(
                    model_name="admin",
                    name="project_code",
                    field=models.CharField(blank=True, db_default="", default="", max_length=20),
                ),
                migrations.AddField(
                    model_name="item",
                    name="sub_inventory",
                    field=models.CharField(blank=True, db_default="", default="", max_length=120),
                ),
                migrations.AddField(
                    model_name="item",
                    name="arabic_name",
                    field=models.CharField(blank=True, db_default="", default="", max_length=250),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    lambda apps, schema_editor: ensure_models(
                        schema_editor, ("Admin", "Item")
                    ),
                    migrations.RunPython.noop,
                )
            ],
        ),
    ]
