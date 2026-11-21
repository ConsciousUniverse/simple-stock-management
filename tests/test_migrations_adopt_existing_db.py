"""The deploy must survive a database that predates migrations.

Production was created by ``migrate --run-syncdb`` at several points in the
project's life, so its tables exist but a table or a column added later can be
missing. ``--fake-initial`` only notices a missing *table*; when one is absent
it falls back to creating everything and dies on the first table that is already
there ("relation stock_manager_admin already exists").

These tests drive ``manage.py migrate`` in a subprocess against a real SQLite
file, first with a complete schema, then with the drift above, which is the
shape of the production database that failed.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 35, 0),
    reason="DROP COLUMN needs SQLite 3.35 or newer",
)


def _env(db_path: Path) -> dict:
    env = dict(os.environ)
    env.update(
        DJANGO_SETTINGS_MODULE="ssm.settings",
        DJANGO_DEBUG="True",
        DJANGO_SECRET_KEY="test",
        DJANGO_ALLOWED_HOSTS="localhost",
        DB_NAME=str(db_path),
        LOG_FILE=str(db_path.with_suffix(".log")),
        ALLOW_PW_CHANGE="True",
        AXES_FAILURE_LIMIT="50",
        AXES_COOLOFF_TIME="1",
    )
    return env


def _migrate(db_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "manage.py", "migrate", "--run-syncdb", "--noinput"],
        cwd=ROOT,
        env=_env(db_path),
        capture_output=True,
        text=True,
        timeout=300,
    )


def _tables(db_path: Path) -> set:
    with sqlite3.connect(db_path) as connection:
        return {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }


def _columns(db_path: Path, table: str) -> set:
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute(f"pragma table_info({table})")}


@pytest.fixture()
def legacy_database(tmp_path):
    """A migrated database whose schema has drifted, with no migration record."""
    db_path = tmp_path / "legacy.sqlite3"
    first = _migrate(db_path)
    assert first.returncode == 0, first.stderr[-3000:]

    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE stock_manager_transferitem")
        connection.execute(
            "ALTER TABLE stock_manager_stockdocument DROP COLUMN decided_at"
        )
        connection.execute("DELETE FROM django_migrations WHERE app = 'stock_manager'")
    return db_path


def test_a_missing_table_and_column_are_created_instead_of_failing(legacy_database):
    assert "stock_manager_transferitem" not in _tables(legacy_database)

    result = _migrate(legacy_database)

    assert result.returncode == 0, result.stderr[-3000:]
    assert "stock_manager_transferitem" in _tables(legacy_database)
    assert "decided_at" in _columns(legacy_database, "stock_manager_stockdocument")


def test_the_new_tables_arrive_on_the_same_run(legacy_database):
    _migrate(legacy_database)

    tables = _tables(legacy_database)
    assert "stock_manager_auditevent" in tables
    assert "stock_manager_apprelease" in tables
    assert "unit" in _columns(legacy_database, "stock_manager_item")


def test_a_second_run_changes_nothing(legacy_database):
    _migrate(legacy_database)

    again = _migrate(legacy_database)

    assert again.returncode == 0, again.stderr[-3000:]
    assert "No migrations to apply" in again.stdout


def test_a_fresh_database_still_gets_every_table(tmp_path):
    db_path = tmp_path / "fresh.sqlite3"

    result = _migrate(db_path)

    assert result.returncode == 0, result.stderr[-3000:]
    tables = _tables(db_path)
    for table in (
        "stock_manager_admin",
        "stock_manager_item",
        "stock_manager_shopitem",
        "stock_manager_transferitem",
        "stock_manager_goodsreceipt",
        "stock_manager_goodsreceiptline",
        "stock_manager_stockdocument",
        "stock_manager_stockdocumentline",
        "stock_manager_auditevent",
        "stock_manager_apprelease",
    ):
        assert table in tables, table
    assert "unit" in _columns(db_path, "stock_manager_item")


def teardown_module(module):
    # The subprocess writes a log next to each database; tmp_path cleans the
    # databases themselves.
    for leftover in Path("/tmp").glob("legacy*.log"):
        leftover.unlink(missing_ok=True)
