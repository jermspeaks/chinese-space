#!/usr/bin/env python3
"""Local browser interface for the Hanly vocabulary database."""

import argparse
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from hanly_index.database import DEFAULT_DB, connect, initialize
from hanly_index.reading_analysis import analyze_reading
from hanly_index.repository import (
    add_personal_note,
    character_statuses,
    dashboard_counts,
    get_entry_detail,
    save_lookup,
    search_entries,
    update_learning_status,
    upsert_entry,
)
from hanly_index.templates import article_analysis, article_form, dashboard, entry_detail, page

STATIC_DIR = Path(__file__).resolve().parent / "hanly_index" / "static"
STATUSES = ("new", "learning", "known", "suspended")
NOTE_TYPES = ("general", "decomposition", "mnemonic", "usage", "writing")


class Handler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB

    def respond(self, body, status=200, content_type="text/html; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def form(self):
        length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
        values = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        return {key: items[0].strip() for key, items in values.items()}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/static/style.css":
            self.respond((STATIC_DIR / "style.css").read_text(encoding="utf-8"), content_type="text/css; charset=utf-8")
            return
        if parsed.path == "/article":
            self.respond(article_form())
            return
        if parsed.path.startswith("/entry/"):
            try:
                self.show_entry(int(parsed.path.rsplit("/", 1)[1]))
            except ValueError:
                self.respond(page("Not found", "<h1>Entry not found</h1>"), 404)
            return
        if parsed.path != "/":
            self.respond(page("Not found", "<h1>Page not found</h1>"), 404)
            return
        self.show_index(parse_qs(parsed.query))

    def show_index(self, query):
        term = query.get("q", [""])[0].strip()
        kind = query.get("kind", [""])[0]
        status = query.get("status", [""])[0]
        missing = query.get("missing", [""])[0]
        new_character = query.get("new", [""])[0]
        try:
            offset = max(0, int(query.get("offset", ["0"])[0]))
        except ValueError:
            offset = 0
        with connect(self.db_path) as db:
            counts = dashboard_counts(db)
            total, rows = search_entries(db, term, kind, status, missing, offset)
        self.respond(dashboard(
            counts, rows, term=term, kind=kind, status=status, missing=missing,
            offset=offset, total=total, new_character=new_character,
        ))

    def show_entry(self, entry_id):
        with connect(self.db_path) as db:
            data = get_entry_detail(db, entry_id)
        if data is None:
            self.respond(page("Not found", "<h1>Entry not found</h1>"), 404)
            return
        self.respond(entry_detail(data))

    def do_POST(self):
        path = urlparse(self.path).path
        values = self.form()
        if path == "/article":
            article = values.get("article", "")
            if not article:
                self.respond(page("Analyze a reading", "<p>Please paste some Chinese text.</p>"), 400)
                return
            with connect(self.db_path) as db:
                statuses = character_statuses(db)
            result = analyze_reading(article, statuses)
            self.respond(article_analysis(result))
            return

        with connect(self.db_path) as db:
            if path == "/add":
                kind, simplified = values.get("kind"), values.get("simplified", "")
                if kind not in ("character", "word") or not simplified:
                    self.respond(page("Invalid entry", "<p>Please provide a kind and simplified headword.</p>"), 400)
                    return
                entry_id = upsert_entry(
                    db, kind, simplified, values.get("traditional") or None,
                    values.get("pinyin", ""), values.get("meaning", ""), "manual",
                )
                self.redirect(f"/entry/{entry_id}")
                return

            match = re.fullmatch(r"/entry/(\d+)/(status|note|lookup)", path)
            if not match:
                self.respond(page("Not found", "<h1>Page not found</h1>"), 404)
                return
            entry_id, action = int(match.group(1)), match.group(2)
            if not db.execute("SELECT 1 FROM entries WHERE id=?", (entry_id,)).fetchone():
                self.respond(page("Not found", "<h1>Entry not found</h1>"), 404)
                return
            if action == "status":
                status = values.get("status")
                if status not in STATUSES:
                    self.respond(page("Invalid status", "<p>Unknown learning status.</p>"), 400)
                    return
                update_learning_status(db, entry_id, status)
            elif action == "note":
                body, note_type = values.get("body", ""), values.get("note_type", "general")
                if not body or note_type not in NOTE_TYPES:
                    self.respond(page("Invalid note", "<p>Provide a note and valid note type.</p>"), 400)
                    return
                add_personal_note(db, entry_id, note_type, body)
            elif action == "lookup":
                save_lookup(db, entry_id, values.get("pinyin", ""), values.get("meaning", ""), values.get("source") or "manual")
        self.redirect(f"/entry/{entry_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"Database not found at {args.db}; run `python3 hanly_db.py init` first.")
    initialize(args.db)
    Handler.db_path = args.db
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Hanly Index is running at http://127.0.0.1:{args.port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Hanly Index.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
