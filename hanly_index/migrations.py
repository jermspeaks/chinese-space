"""Ordered, versioned SQLite schema migrations."""


def _ensure_column(db, table, column, definition):
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _initial_schema(db, schema_file):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entries'").fetchone()
    if exists is None:
        schema = schema_file.read_text(encoding="utf-8")
        db.executescript("BEGIN IMMEDIATE;\n" + schema + "\nCOMMIT;")


def _dictionary_provenance(db, _schema_file):
    for table in ("readings", "meanings"):
        _ensure_column(db, table, "source", "TEXT")
        _ensure_column(db, table, "source_license", "TEXT")


MIGRATIONS = (
    (1, "initial schema", _initial_schema),
    (2, "dictionary provenance", _dictionary_provenance),
)


def apply_migrations(db, schema_file):
    db.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
           )"""
    )
    applied = {row["version"] for row in db.execute("SELECT version FROM schema_migrations")}
    for version, name, migrate in MIGRATIONS:
        if version in applied:
            continue
        migrate(db, schema_file)
        db.execute("INSERT INTO schema_migrations(version,name) VALUES(?,?)", (version, name))
