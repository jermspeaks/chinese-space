#!/usr/bin/env python3
"""Small standard-library CLI for the local Hanly vocabulary index."""

import argparse
import csv
import gzip
import json
import re
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "hanly.sqlite"
CC_CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CC_CEDICT_LICENSE = "CC BY-SA 4.0"


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(path):
    with connect(path) as db:
        db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        # Additive migration for databases initialized before dictionary provenance existed.
        for table in ("readings", "meanings"):
            columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for column in ("source", "source_license"):
                if column not in columns:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")


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


def fetch_cedict(args):
    args.output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(CC_CEDICT_URL, headers={"User-Agent": "HanlyIndex/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        with gzip.GzipFile(fileobj=response) as compressed, args.output.open("wb") as output:
            while chunk := compressed.read(1024 * 1024):
                output.write(chunk)
    print(f"Downloaded CC-CEDICT to {args.output}")


def pinyin_with_tones(numbered):
    tone_marks = {
        "a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ",
        "A": "ĀÁǍÀ", "E": "ĒÉĚÈ", "I": "ĪÍǏÌ", "O": "ŌÓǑÒ", "U": "ŪÚǓÙ", "Ü": "ǕǗǙǛ",
    }
    output = []
    for syllable in numbered.split():
        syllable = syllable.replace("u:", "ü").replace("U:", "Ü").replace("v", "ü").replace("V", "Ü")
        match = re.search(r"([1-5])$", syllable)
        if not match:
            output.append(syllable)
            continue
        tone = int(match.group(1))
        base = syllable[:-1]
        if tone == 5:
            output.append(base)
            continue
        low = base.lower()
        target = "a" if "a" in low else "e" if "e" in low else "o" if "ou" in low else ""
        if not target:
            target = next((char.lower() for char in reversed(base) if char.lower() in "aeiouü"), "")
        if target:
            index = next(i for i, char in enumerate(base) if char.lower() == target)
            marked = tone_marks[base[index]][tone - 1]
            base = base[:index] + marked + base[index + 1:]
        output.append(base)
    return " ".join(output).lower()


def cedict_entries(path):
    """Yield (traditional, simplified, pinyin, definitions) from CC-CEDICT text."""
    pattern = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.*)/$")
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            match = pattern.match(line)
            if not match:
                raise SystemExit(f"Could not parse CC-CEDICT line {line_number}: {line[:100]}")
            traditional, simplified, pinyin, raw_definitions = match.groups()
            definitions = [item.strip() for item in raw_definitions.split("/") if item.strip()]
            yield traditional, simplified, pinyin_with_tones(pinyin), definitions


def enrich_cedict(args):
    dictionary = {}
    for record in cedict_entries(args.file):
        dictionary.setdefault(record[1], []).append(record)
    matched = set()
    reading_count = meaning_count = 0
    with connect(args.db) as db:
        for entry in db.execute("SELECT id, simplified FROM entries").fetchall():
            records = dictionary.get(entry["simplified"])
            if not records:
                continue
            matched.add(entry["id"])
            for traditional, _simplified, pinyin, definitions in records:
                db.execute(
                    "UPDATE entries SET traditional = COALESCE(traditional, ?), "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = ?",
                    (traditional, entry["id"]),
                )
                before = db.total_changes
                db.execute(
                    "INSERT OR IGNORE INTO readings (entry_id, pinyin, is_primary, source, source_license) "
                    "VALUES (?, ?, 0, 'CC-CEDICT', ?)",
                    (entry["id"], pinyin, CC_CEDICT_LICENSE),
                )
                reading_count += db.total_changes - before
                for definition in definitions:
                    before = db.total_changes
                    db.execute(
                        "INSERT OR IGNORE INTO meanings "
                        "(entry_id, meaning, meaning_order, source, source_license) "
                        "VALUES (?, ?, (SELECT COALESCE(MAX(meaning_order), -1) + 1 "
                        "FROM meanings WHERE entry_id = ?), 'CC-CEDICT', ?)",
                        (entry["id"], definition, entry["id"], CC_CEDICT_LICENSE),
                    )
                    meaning_count += db.total_changes - before
    print(f"Matched {len(matched)} database entries; added {reading_count} readings and {meaning_count} definitions.")


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
    fetch = commands.add_parser("fetch-cedict", help="download CC-CEDICT into the ignored data directory")
    fetch.add_argument("--output", type=Path, default=ROOT / "data" / "dictionaries" / "cedict_ts.u8")
    fetch.set_defaults(func=fetch_cedict)
    enrich = commands.add_parser("enrich-cedict", help="add matching CC-CEDICT pinyin and definitions")
    enrich.add_argument("file", type=Path, help="unzipped CC-CEDICT cedict_ts.u8 text file")
    enrich.set_defaults(func=enrich_cedict)
    args = parser.parse_args()
    if args.command != "init" and not args.db.exists():
        raise SystemExit(f"Database not found at {args.db}; run `python3 hanly_db.py init` first.")
    args.func(args)


if __name__ == "__main__":
    main()
