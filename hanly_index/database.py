"""SQLite connections and schema initialization."""

import sqlite3
from pathlib import Path

from .migrations import apply_migrations

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "hanly.sqlite"
SCHEMA_FILE = ROOT / "schema.sql"


def connect(path=DEFAULT_DB):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(path=DEFAULT_DB):
    """Initialize or upgrade the database using its migration history."""
    with connect(path) as db:
        apply_migrations(db, SCHEMA_FILE)
