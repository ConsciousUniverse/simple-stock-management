"""Create the models' tables and columns only where they are missing.

The live database predates migrations: its tables were created by
``migrate --run-syncdb`` at different points in the project's life, so a table or
a column added later can be missing. ``--fake-initial`` only notices a missing
*table*; when one is absent it falls back to creating everything and dies on the
first table that is already there ("relation stock_manager_admin already
exists").

Every migration of this app therefore *adopts* the schema instead of assuming it
is empty: create what is absent, leave what is present, and never depend on a
guess about how far the database has come.
"""


def ensure_models(schema_editor, model_names):
    from stock_manager import models

    connection = schema_editor.connection
    with connection.cursor() as cursor:
        existing = set(connection.introspection.table_names(cursor))
    for name in model_names:
        model = getattr(models, name)
        table = model._meta.db_table
        if table not in existing:
            schema_editor.create_model(model)
            continue
        with connection.cursor() as cursor:
            present = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, table
                )
            }
        for field in model._meta.local_fields:
            if field.column not in present:
                schema_editor.add_field(model, field)
