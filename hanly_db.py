#!/usr/bin/env python3
"""Command-line interface for the local Hanly vocabulary index."""

import argparse
from pathlib import Path

from hanly_index.database import DEFAULT_DB, ROOT, connect, initialize
from hanly_index.imports import enrich_cedict, fetch_cedict, import_csv, import_hanly
from hanly_index.repository import add_or_update_entry, add_personal_note, find_entry_id, list_entry_rows


def add_entry_command(args):
    with connect(args.db) as db:
        entry_id = add_or_update_entry(
            db, args.kind, args.text, args.traditional, args.status,
            args.source, args.pinyin, args.meaning,
        )
    print(f"Saved {args.kind} {args.text} (id {entry_id})")


def add_note_command(args):
    try:
        with connect(args.db) as db:
            entry_id = find_entry_id(db, args.text)
            add_personal_note(db, entry_id, args.type, args.text_note)
    except LookupError:
        raise SystemExit(f"No entry found for {args.text!r}; add it first.")
    print(f"Added {args.type} note to {args.text}")


def list_command(args):
    with connect(args.db) as db:
        rows = list_entry_rows(db, args.status)
    for row in rows:
        print("\t".join(str(row[key] or "") for key in
                         ("kind", "simplified", "traditional", "pinyin", "meanings", "learning_status")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite file (default: hanly.sqlite)")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create the database schema or apply migrations")
    init.set_defaults(func=lambda args: (initialize(args.db), print(f"Initialized {args.db}")))

    add = commands.add_parser("add", help="add or update a character/word")
    add.add_argument("kind", choices=("character", "word"))
    add.add_argument("text", help="simplified headword")
    add.add_argument("--traditional")
    add.add_argument("--pinyin")
    add.add_argument("--meaning")
    add.add_argument("--status", choices=("new", "learning", "known", "suspended"), default="new")
    add.add_argument("--source")
    add.set_defaults(func=add_entry_command)

    note = commands.add_parser("note", help="add a personal note")
    note.add_argument("text", help="headword to annotate")
    note.add_argument("--type", choices=("general", "decomposition", "mnemonic", "usage", "writing"), default="general")
    note.add_argument("--text", dest="text_note", required=True, help="note body")
    note.set_defaults(func=add_note_command)

    listing = commands.add_parser("list", help="list entries as tab-separated rows")
    listing.add_argument("--status", choices=("new", "learning", "known", "suspended"))
    listing.set_defaults(func=list_command)

    importer = commands.add_parser("import-csv", help="import entries from a CSV file")
    importer.add_argument("file", type=Path)
    importer.set_defaults(func=lambda args: print(f"Imported or updated {import_csv(args.file, args.db)} entries from {args.file}"))

    hanly = commands.add_parser("import-hanly", help="import a Hanly learning progress JSON export")
    hanly.add_argument("file", type=Path)
    def import_hanly_command(args):
        count = import_hanly(args.file, args.db)
        if count is None:
            print(f"This Hanly export is already imported: {args.file.name}")
        else:
            print(f"Imported {count} Hanly progress records from {args.file.name}")
    hanly.set_defaults(func=import_hanly_command)

    fetch = commands.add_parser("fetch-cedict", help="download CC-CEDICT into the ignored data directory")
    fetch.add_argument("--output", type=Path, default=ROOT / "data" / "dictionaries" / "cedict_ts.u8")
    fetch.set_defaults(func=lambda args: print(f"Downloaded CC-CEDICT to {fetch_cedict(args.output)}"))

    enrich = commands.add_parser("enrich-cedict", help="add matching CC-CEDICT pinyin and definitions")
    enrich.add_argument("file", type=Path, help="unzipped CC-CEDICT cedict_ts.u8 text file")
    def enrich_command(args):
        matched, readings, meanings = enrich_cedict(args.file, args.db)
        print(f"Matched {matched} database entries; added {readings} readings and {meanings} definitions.")
    enrich.set_defaults(func=enrich_command)

    args = parser.parse_args()
    if args.command != "init" and args.command not in ("fetch-cedict",) and not args.db.exists():
        raise SystemExit(f"Database not found at {args.db}; run `python3 hanly_db.py init` first.")
    try:
        args.func(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
