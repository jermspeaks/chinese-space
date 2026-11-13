#!/usr/bin/env python3
"""Small standard-library CLI for the local Hanly vocabulary index."""

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "hanly.sqlite"


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(path):
    with connect(path) as db:
        db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))


def get_entry(db, value):
    row = db.execute(
        "SELECT id FROM entries WHERE simplified = ? ORDER BY kind LIMIT 1", (value,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"No entry found for {value!r}; add it first.")
    return row["id"]


def add_entry(args):
    with connect(args.db) as db:
        db.execute(
            """INSERT INTO entries (kind, simplified, traditional, learning_status, source)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(kind, simplified) DO UPDATE SET
                 traditional = COALESCE(excluded.traditional, entries.traditional),
                 learning_status = excluded.learning_status,
                 source = COALESCE(excluded.source, entries.source),
                 updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
            (args.kind, args.text, args.traditional, args.status, args.source),
        )
        entry_id = db.execute(
            "SELECT id FROM entries WHERE kind = ? AND simplified = ?",
            (args.kind, args.text),
        ).fetchone()["id"]
        if args.pinyin:
            db.execute(
                "INSERT OR IGNORE INTO readings (entry_id, pinyin, is_primary) VALUES (?, ?, 1)",
                (entry_id, args.pinyin),
            )
        if args.meaning:
            db.execute(
                "INSERT INTO meanings (entry_id, meaning, meaning_order) "
                "SELECT ?, ?, COALESCE(MAX(meaning_order), -1) + 1 FROM meanings WHERE entry_id = ?",
                (entry_id, args.meaning, entry_id),
            )
        print(f"Saved {args.kind} {args.text} (id {entry_id})")


def add_note(args):
    with connect(args.db) as db:
        entry_id = get_entry(db, args.text)
        db.execute(
            "INSERT INTO notes (entry_id, note_type, body) VALUES (?, ?, ?)",
            (entry_id, args.type, args.text_note),
        )
        print(f"Added {args.type} note to {args.text}")


def list_entries(args):
    query = "SELECT * FROM entry_summary"
    values = []
    if args.status:
        query += " WHERE learning_status = ?"
        values.append(args.status)
    query += " ORDER BY simplified"
    with connect(args.db) as db:
        for row in db.execute(query, values):
            print("\t".join(str(row[key] or "") for key in
                            ("kind", "simplified", "traditional", "pinyin", "meanings", "learning_status")))


def import_csv(args):
    required = {"kind", "simplified"}
    allowed_status = {"new", "learning", "known", "suspended"}
    count = 0
    with args.file.open(newline="", encoding="utf-8-sig") as source, connect(args.db) as db:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise SystemExit("CSV must have at least these columns: kind,simplified")
        for line, row in enumerate(reader, start=2):
            kind = (row.get("kind") or "").strip()
            simplified = (row.get("simplified") or "").strip()
            if kind not in ("character", "word") or not simplified:
                raise SystemExit(f"Invalid kind or missing simplified text on CSV line {line}")
            status = (row.get("status") or "new").strip() or "new"
            if status not in allowed_status:
                raise SystemExit(f"Invalid status {status!r} on CSV line {line}")
            db.execute(
                """INSERT INTO entries (kind, simplified, traditional, learning_status, source, source_id)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(kind, simplified) DO UPDATE SET
                     traditional = COALESCE(excluded.traditional, entries.traditional),
                     learning_status = excluded.learning_status,
                     source = COALESCE(excluded.source, entries.source),
                     source_id = COALESCE(excluded.source_id, entries.source_id),
                     updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (kind, simplified, (row.get("traditional") or "").strip() or None,
                 status, (row.get("source") or "").strip() or None,
                 (row.get("source_id") or "").strip() or None),
            )
            entry_id = db.execute(
                "SELECT id FROM entries WHERE kind = ? AND simplified = ?", (kind, simplified)
            ).fetchone()["id"]
            for pinyin in (row.get("pinyin") or "").split(";"):
                pinyin = pinyin.strip()
                if pinyin:
                    db.execute(
                        "INSERT OR IGNORE INTO readings (entry_id, pinyin, is_primary) VALUES (?, ?, ?)",
                        (entry_id, pinyin, int(not db.execute(
                            "SELECT 1 FROM readings WHERE entry_id = ?", (entry_id,)
                        ).fetchone())),
                    )
            for meaning in (row.get("meaning") or "").split(";"):
                meaning = meaning.strip()
                if meaning:
                    db.execute(
                        "INSERT OR IGNORE INTO meanings (entry_id, meaning, meaning_order) "
                        "VALUES (?, ?, (SELECT COALESCE(MAX(meaning_order), -1) + 1 FROM meanings WHERE entry_id = ?))",
                        (entry_id, meaning, entry_id),
                    )
            count += 1
    print(f"Imported or updated {count} entries from {args.file}")


def import_hanly(args):
    source_file = args.file.name
    match = re.search(r"(\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d)", source_file)
    if match:
        exported_at = f"{match.group(1)[:10]}T{match.group(1)[11:13]}:{match.group(1)[14:16]}:{match.group(1)[17:19]}"
    else:
        exported_at = "unknown"
    data = json.loads(args.file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Hanly export must be a JSON object keyed by entry text")

    valid = {}
    for key, progress in data.items():
        if not isinstance(key, str) or not isinstance(progress, dict):
            raise SystemExit(f"Unexpected Hanly record for key {key!r}")
        percent = progress.get("progressPercent")
        status = progress.get("learningStatus")
        if not isinstance(percent, (int, float)) or not 0 <= percent <= 1 or not isinstance(status, str):
            raise SystemExit(f"Invalid progress fields for Hanly key {key!r}")
        reverse = key.endswith("_reverse")
        simplified = key[:-8] if reverse else key
        if not simplified:
            raise SystemExit(f"Empty entry in Hanly key {key!r}")
        valid[key] = (simplified, "reverse" if reverse else "forward", float(percent), status)

    with connect(args.db) as db:
        batch = db.execute(
            "INSERT INTO learning_progress_exports (source_file, exported_at) VALUES (?, ?) "
            "ON CONFLICT(source_file) DO NOTHING RETURNING id",
            (source_file, exported_at),
        ).fetchone()
        if batch is None:
            print(f"This Hanly export is already imported: {source_file}")
            return
        export_id = batch["id"]
        for source_key, (simplified, direction, percent, status) in valid.items():
            kind = "character" if len(simplified) == 1 else "word"
            db.execute(
                """INSERT INTO entries (kind, simplified, learning_status, source, source_id)
                   VALUES (?, ?, 'learning', 'Hanly', ?)
                   ON CONFLICT(kind, simplified) DO UPDATE SET
                     source = COALESCE(entries.source, excluded.source),
                     source_id = COALESCE(entries.source_id, excluded.source_id)""",
                (kind, simplified, simplified),
            )
            entry_id = db.execute(
                "SELECT id FROM entries WHERE kind = ? AND simplified = ?", (kind, simplified)
            ).fetchone()["id"]
            db.execute(
                """INSERT INTO entry_progress
                   (export_id, entry_id, source_key, direction, progress_percent, learning_status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (export_id, entry_id, source_key, direction, percent, status),
            )
    print(f"Imported {len(valid)} Hanly progress records from {source_file}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file (default: hanly.sqlite)")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="create the database schema")
    init.set_defaults(func=lambda args: (initialize(args.db), print(f"Initialized {args.db}")))
    add = commands.add_parser("add", help="add or update a character/word")
    add.add_argument("kind", choices=("character", "word"))
    add.add_argument("text", help="simplified headword")
    add.add_argument("--traditional")
    add.add_argument("--pinyin")
    add.add_argument("--meaning")
    add.add_argument("--status", choices=("new", "learning", "known", "suspended"), default="new")
    add.add_argument("--source")
    add.set_defaults(func=add_entry)
    note = commands.add_parser("note", help="add a personal note")
    note.add_argument("text", help="headword to annotate")
    note.add_argument("--type", choices=("general", "decomposition", "mnemonic", "usage", "writing"), default="general")
    note.add_argument("--text", dest="text_note", required=True, help="note body")
    note.set_defaults(func=add_note)
    listing = commands.add_parser("list", help="list entries as tab-separated rows")
    listing.add_argument("--status", choices=("new", "learning", "known", "suspended"))
    listing.set_defaults(func=list_entries)
    importer = commands.add_parser("import-csv", help="import entries from a CSV file")
    importer.add_argument("file", type=Path)
    importer.set_defaults(func=import_csv)
    hanly = commands.add_parser("import-hanly", help="import a Hanly learning progress JSON export")
    hanly.add_argument("file", type=Path)
    hanly.set_defaults(func=import_hanly)
    args = parser.parse_args()
    if args.command != "init" and not args.db.exists():
        raise SystemExit(f"Database not found at {args.db}; run `python3 hanly_db.py init` first.")
    args.func(args)


if __name__ == "__main__":
    main()
