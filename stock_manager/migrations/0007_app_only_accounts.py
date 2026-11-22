"""An account that signs in from the phone and nowhere else.

The column is what the web sign-in form reads to refuse such an account by
name, so it has to exist on the live database — which predates migrations and
would ignore a ``CreateModel``. ``ensure_models`` adds the column and leaves
everything else alone.
"""

from django.db import migrations, models

from ._adopt import ensure_models


def adopt_profile(apps, schema_editor):
    ensure_models(schema_editor, ("MobileProfile",))


class Migration(migrations.Migration):

    dependencies = [
        ("stock_manager", "0006_mobile_app"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="mobileprofile",
                    name="mobile_only",
                    field=models.BooleanField(default=False),
                ),
            ],
            database_operations=[
                migrations.RunPython(adopt_profile, migrations.RunPython.noop),
            ],
        ),
    ]
