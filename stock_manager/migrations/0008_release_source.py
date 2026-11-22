"""Record where a release row came from: typed by a person, or read from GitHub.

The server now mirrors the published releases into this table so the answer to
"is there an update?" survives a GitHub outage. The mirror must be
distinguishable from a row a manager typed, because only the typed one may act
as a deliberate pin.
"""

from django.db import migrations, models

from ._adopt import ensure_models


class Migration(migrations.Migration):

    dependencies = [("stock_manager", "0007_app_only_accounts")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="apprelease",
                    name="source",
                    field=models.CharField(default="manual", max_length=20),
                )
            ],
            database_operations=[
                migrations.RunPython(
                    lambda apps, schema_editor: ensure_models(
                        schema_editor, ("AppRelease",)
                    ),
                    migrations.RunPython.noop,
                )
            ],
        )
    ]
