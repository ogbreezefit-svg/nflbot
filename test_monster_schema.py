"""Schema tests run in subprocesses against in-memory SQLite only."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class MonsterSchemaTests(unittest.TestCase):
    def run_isolated(self, script):
        env = os.environ.copy()
        env["DATABASE_URL"] = "sqlite:///:memory:"
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stdout + "\n" + result.stderr,
        )

    def test_new_schema_has_nullable_approval_fields(self):
        self.run_isolated('''
import db
from sqlalchemy import inspect

assert (
    db.engine.url.get_backend_name() == "sqlite"
    and db.engine.url.database == ":memory:"
), (
    "Isolation check failed: "
    f"backend={db.engine.url.get_backend_name()!r}, "
    f"in_memory={db.engine.url.database == ':memory:'}, "
    f"db_module={db.__file__!r}"
)
db.init_db()
columns = {
    column["name"]: column
    for column in inspect(db.engine).get_columns("parlays")
}
for name in (
    "research_qualified",
    "prediction_approved",
    "publication_approved",
    "publication_approval_ref",
):
    assert name in columns, name
    assert columns[name]["nullable"] is True, name
''')

    def test_old_ticket_stays_unapproved_after_migration(self):
        self.run_isolated('''
import db
from sqlalchemy import text

assert (
    db.engine.url.get_backend_name() == "sqlite"
    and db.engine.url.database == ":memory:"
), (
    "Isolation check failed: "
    f"backend={db.engine.url.get_backend_name()!r}, "
    f"in_memory={db.engine.url.database == ':memory:'}, "
    f"db_module={db.__file__!r}"
)
with db.engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE parlays (
            id INTEGER PRIMARY KEY,
            category VARCHAR,
            odds VARCHAR,
            stake VARCHAR,
            payout VARCHAR,
            legs_json TEXT,
            status VARCHAR,
            created_at DATETIME
        )
    """))
    conn.execute(text("""
        INSERT INTO parlays (id, category, legs_json, status)
        VALUES (1, 'Weekly Monster', '[]', 'ACTIVE')
    """))

db.init_db()
db.init_db()

with db.engine.connect() as conn:
    row = conn.execute(text("""
        SELECT category, publication_mode, research_qualified,
               prediction_approved, publication_approved,
               publication_approval_ref
        FROM parlays WHERE id = 1
    """)).mappings().one()

assert row["category"] == "Weekly Monster"
for name in (
    "publication_mode",
    "research_qualified",
    "prediction_approved",
    "publication_approved",
    "publication_approval_ref",
):
    assert row[name] is None, (name, row[name])
''')


if __name__ == "__main__":
    unittest.main()
