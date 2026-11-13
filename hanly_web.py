#!/usr/bin/env python3
"""Local browser interface for the Hanly vocabulary database."""

import argparse
import html
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from hanly_db import DEFAULT_DB, initialize
from hanly_db import connect as connect_db

STATUSES = ("new", "learning", "known", "suspended")
NOTE_TYPES = ("general", "decomposition", "mnemonic", "usage", "writing")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u{20000}-\u{2fa1f}]")

STYLE = """
:root{color-scheme:light;--ink:#202522;--muted:#6b746e;--line:#e2e7e3;--paper:#f7f8f5;--green:#315e49;--pale:#e9f1eb}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
a{color:var(--green)}header{padding:23px max(24px,calc((100% - 1180px)/2));background:#fff;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
header a{text-decoration:none;font-weight:700;font-size:19px}.wrap{max-width:1180px;margin:28px auto;padding:0 20px}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:20px 0}
.stat,.panel,.entry{background:#fff;border:1px solid var(--line);border-radius:10px}.stat{padding:14px 17px}.stat strong{font-size:25px;display:block}.stat span,.muted{color:var(--muted);font-size:13px}
.panel{padding:18px;margin:18px 0}.filters,.inline{display:flex;gap:10px;align-items:end;flex-wrap:wrap}.filters label,.field{display:grid;gap:5px;color:var(--muted);font-size:13px;flex:1;min-width:140px}
input,select,textarea,button{font:inherit;border:1px solid #cfd7d0;border-radius:6px;padding:9px 10px;background:#fff;color:var(--ink)}textarea{min-height:90px;resize:vertical}button,.button{border:0;background:var(--green);color:white;cursor:pointer;text-decoration:none;padding:10px 14px;border-radius:6px;font-weight:600}.button.secondary{background:var(--pale);color:var(--green)}
.list{display:grid;gap:8px}.entry{padding:13px 15px;display:grid;grid-template-columns:minmax(100px,1fr) 2fr minmax(165px,1fr);gap:12px;align-items:center;text-decoration:none;color:inherit}.entry:hover{border-color:#91aa98}.hanzi{font-size:23px}.entry .meaning{color:#455149}.tag{display:inline-block;background:var(--pale);color:var(--green);border-radius:99px;padding:2px 9px;font-size:12px}
.detail-title{font-size:42px;margin:0}.detail-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.note{padding:12px 0;border-bottom:1px solid var(--line);white-space:pre-wrap}.note:last-child{border:0}.pagination{display:flex;justify-content:space-between;margin:18px 0}.topline{display:flex;justify-content:space-between;align-items:center;gap:10px}
@media(max-width:720px){.stats{grid-template-columns:repeat(2,1fr)}.entry{grid-template-columns:1fr}.detail-grid{grid-template-columns:1fr}.wrap{margin-top:16px}header{padding:17px 20px}}
"""


def esc(value):
    return html.escape(str(value or ""), quote=True)


def page(title, content):
    return f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{esc(title)} · Hanly Index</title><style>{STYLE}</style><body><header><a href='/'>Hanly Index</a><span class='muted'>Local vocabulary database</span></header><main class='wrap'>{content}</main></body></html>"


class Handler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB

    def respond(self, body, status=200):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
        try:
            offset = max(0, int(query.get("offset", ["0"])[0]))
        except ValueError:
            offset = 0

        with connect_db(self.db_path) as db:
            total = db.execute("SELECT count(*) FROM entries").fetchone()[0]
            characters = db.execute("SELECT count(*) FROM entries WHERE kind='character'").fetchone()[0]
            words = db.execute("SELECT count(*) FROM entries WHERE kind='word'").fetchone()[0]
            known = db.execute("SELECT count(*) FROM entries WHERE learning_status='known'").fetchone()[0]
            coverage = db.execute("SELECT count(DISTINCT entry_id) FROM readings WHERE source='CC-CEDICT'").fetchone()[0]
            where, params = [], []
            if kind in ("character", "word"):
                where.append("e.kind = ?"); params.append(kind)
            if status in STATUSES:
                where.append("e.learning_status = ?"); params.append(status)
            if term:
                pattern = f"%{term}%"
                where.append("(e.simplified LIKE ? OR e.traditional LIKE ? OR EXISTS (SELECT 1 FROM readings r WHERE r.entry_id=e.id AND r.pinyin LIKE ?) OR EXISTS (SELECT 1 FROM meanings m WHERE m.entry_id=e.id AND m.meaning LIKE ?))")
                params.extend((pattern, pattern, pattern, pattern))
            if missing == "dictionary":
                where.append("NOT EXISTS (SELECT 1 FROM meanings m WHERE m.entry_id=e.id AND m.source='CC-CEDICT')")
            elif missing == "reading":
                where.append("NOT EXISTS (SELECT 1 FROM readings r WHERE r.entry_id=e.id)")
            condition = " WHERE " + " AND ".join(where) if where else ""
            count = db.execute("SELECT count(*) FROM entries e" + condition, params).fetchone()[0]
            rows = db.execute(
                """SELECT e.id,e.kind,e.simplified,e.traditional,e.learning_status,
                   (SELECT group_concat(r.pinyin, '; ') FROM readings r WHERE r.entry_id=e.id) pinyin,
                   (SELECT group_concat(meaning, '; ') FROM (SELECT m.meaning FROM meanings m WHERE m.entry_id=e.id ORDER BY m.meaning_order LIMIT 2)) meanings,
                   (SELECT round(p.progress_percent*100) FROM entry_progress p WHERE p.entry_id=e.id AND p.direction='forward' ORDER BY p.export_id DESC LIMIT 1) forward_progress,
                   (SELECT round(p.progress_percent*100) FROM entry_progress p WHERE p.entry_id=e.id AND p.direction='reverse' ORDER BY p.export_id DESC LIMIT 1) reverse_progress
                   FROM entries e""" + condition + " ORDER BY e.simplified LIMIT 100 OFFSET ?",
                params + [offset],
            ).fetchall()

        def option(group, value, label):
            return f"<option value='{esc(value)}' {'selected' if group == value else ''}>{esc(label)}</option>"

        form = f"""<section class='panel'><form class='filters' method='get'>
        <label>Search<input name='q' value='{esc(term)}' placeholder='Character, word, pinyin, meaning'></label>
        <label>Type<select name='kind'>{option(kind,'','All types')}{option(kind,'character','Characters')}{option(kind,'word','Words')}</select></label>
        <label>Learning status<select name='status'>{option(status,'','All statuses')}{''.join(option(status,s,s.title()) for s in STATUSES)}</select></label>
        <label>Needs attention<select name='missing'>{option(missing,'','Any coverage')}{option(missing,'dictionary','Missing CC-CEDICT definitions')}{option(missing,'reading','Missing pinyin')}</select></label>
        <button>Filter</button></form></section>"""
        stats = f"<section class='stats'><div class='stat'><strong>{total:,}</strong><span>Entries</span></div><div class='stat'><strong>{characters:,}</strong><span>Characters</span></div><div class='stat'><strong>{words:,}</strong><span>Words</span></div><div class='stat'><strong>{known:,}</strong><span>Marked known</span></div><div class='stat'><strong>{coverage:,}</strong><span>CC-CEDICT covered</span></div></section>"
        add_form = """<details class='panel'><summary><strong>Add a character or word</strong></summary><form method='post' action='/add' class='filters' style='margin-top:14px'>
        <label>Type<select name='kind'><option value='character'>Character</option><option value='word'>Word</option></select></label>
        <label>Simplified<input name='simplified' required></label><label>Traditional<input name='traditional'></label>
        <label>Pinyin<input name='pinyin' placeholder='nǐ hǎo'></label><label>Meaning<input name='meaning'></label><button>Add entry</button></form></details>"""
        rendered = []
        for row in rows:
            progress = []
            if row["forward_progress"] is not None:
                progress.append(f"Hanly → {row['forward_progress']}%")
            if row["reverse_progress"] is not None:
                progress.append(f"Hanly ← {row['reverse_progress']}%")
            meta = " · ".join(part for part in (row["pinyin"], " / ".join(progress), row["learning_status"]) if part)
            rendered.append(f"<a class='entry' href='/entry/{row['id']}'><span class='hanzi'>{esc(row['simplified'])}<small class='muted'> {esc(row['traditional'])}</small></span><span><span>{esc(meta)}</span><br><span class='meaning'>{esc(row['meanings'])}</span></span><span><span class='tag'>{esc(row['kind'])}</span></span></a>")
        start = min(offset + 1, count) if count else 0
        end = min(offset + len(rows), count)
        prev_url = self.query_url(term, kind, status, missing, max(0, offset - 100))
        next_url = self.query_url(term, kind, status, missing, offset + 100)
        pager = f"<div class='pagination'><span>{start}–{end} of {count:,}</span><span>{f'<a href={quote(prev_url, safe="/?=&%")}>Previous</a>' if offset else ''} &nbsp; {f'<a href={quote(next_url, safe="/?=&%")}>Next</a>' if offset + 100 < count else ''}</span></div>"
        content = f"<div class='topline'><div><h1>Vocabulary</h1><span class='muted'>Search and review your character and word list.</span></div><a class='button secondary' href='/'>Clear filters</a></div>{stats}{form}{add_form}{pager}<div class='list'>{''.join(rendered) if rendered else '<div class="panel">No matching entries.</div>'}</div>{pager}"
        self.respond(page("Vocabulary", content))

    @staticmethod
    def query_url(term, kind, status, missing, offset):
        from urllib.parse import urlencode
        return "/?" + urlencode({k: v for k, v in {"q": term, "kind": kind, "status": status, "missing": missing, "offset": offset}.items() if v})

    def show_entry(self, entry_id):
        with connect_db(self.db_path) as db:
            entry = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not entry:
                self.respond(page("Not found", "<h1>Entry not found</h1>"), 404); return
            readings = db.execute("SELECT pinyin,source,source_license FROM readings WHERE entry_id=? ORDER BY is_primary DESC,pinyin", (entry_id,)).fetchall()
            meanings = db.execute("SELECT meaning,source,source_license FROM meanings WHERE entry_id=? ORDER BY meaning_order,meaning", (entry_id,)).fetchall()
            notes = db.execute("SELECT note_type,body,created_at FROM notes WHERE entry_id=? ORDER BY created_at DESC", (entry_id,)).fetchall()
            progress = db.execute("SELECT direction,round(progress_percent*100) percent,learning_status FROM entry_progress WHERE entry_id=? AND export_id=(SELECT max(export_id) FROM entry_progress WHERE entry_id=?) ORDER BY direction", (entry_id, entry_id)).fetchall()

        status_options = "".join(f"<option value='{s}' {'selected' if entry['learning_status']==s else ''}>{s.title()}</option>" for s in STATUSES)
        readings_html = "".join(f"<li>{esc(r['pinyin'])} <span class='muted'>({esc(r['source'] or 'manual')}{', ' + esc(r['source_license']) if r['source_license'] else ''})</span></li>" for r in readings) or "<li class='muted'>No pronunciation yet</li>"
        meanings_html = "".join(f"<li>{esc(m['meaning'])} <span class='muted'>({esc(m['source'] or 'manual')}{', ' + esc(m['source_license']) if m['source_license'] else ''})</span></li>" for m in meanings) or "<li class='muted'>No meanings yet</li>"
        progress_html = "".join(f"<span class='tag'>Hanly {esc(p['direction'])}: {p['percent']}% · {esc(p['learning_status'])}</span> " for p in progress) or "<span class='muted'>No Hanly progress snapshot</span>"
        notes_html = "".join(f"<div class='note'><span class='tag'>{esc(n['note_type'])}</span><div>{esc(n['body'])}</div><small class='muted'>{esc(n['created_at'])}</small></div>" for n in notes) or "<p class='muted'>No personal notes yet.</p>"
        content = f"""<p><a href='/'>← All entries</a></p><div class='topline'><div><h1 class='detail-title'>{esc(entry['simplified'])} <small class='muted'>{esc(entry['traditional'])}</small></h1><span class='tag'>{esc(entry['kind'])}</span> <span class='muted'>Source: {esc(entry['source'] or 'manual')}</span></div>
        <form method='post' action='/entry/{entry_id}/status' class='inline'><label class='field'>Learning status<select name='status'>{status_options}</select></label><button>Save status</button></form></div>
        <section class='panel'><h2>Hanly progress</h2>{progress_html}</section>
        <div class='detail-grid'><section class='panel'><h2>Pinyin</h2><ul>{readings_html}</ul><h2>Meanings</h2><ul>{meanings_html}</ul></section>
        <section class='panel'><h2>Add dictionary lookup</h2><form method='post' action='/entry/{entry_id}/lookup'><label class='field'>Pinyin<input name='pinyin' placeholder='pinyin with tone marks'></label><label class='field'>Meaning<input name='meaning' placeholder='English gloss'></label><label class='field'>Source<input name='source' value='Pleco'></label><button style='margin-top:10px'>Save lookup</button></form><p class='muted'>This adds a source-attributed reading and/or meaning without replacing existing data.</p></section></div>
        <section class='panel'><h2>Personal notes</h2>{notes_html}<form method='post' action='/entry/{entry_id}/note'><div class='filters'><label>Note type<select name='note_type'>{''.join(f'<option value="{t}">{t.title()}</option>' for t in NOTE_TYPES)}</select></label><label class='field' style='flex:3'>Note<textarea name='body' required placeholder='Decomposition, mnemonic, usage, or writing note'></textarea></label><button>Add note</button></div></form></section>"""
        self.respond(page(entry["simplified"], content))

    def do_POST(self):
        path = urlparse(self.path).path
        values = self.form()
        with connect_db(self.db_path) as db:
            if path == "/add":
                kind, simplified = values.get("kind"), values.get("simplified", "")
                if kind not in ("character", "word") or not simplified:
                    self.respond(page("Invalid entry", "<p>Please provide a kind and simplified headword.</p>"), 400); return
                db.execute("""INSERT INTO entries(kind,simplified,traditional,learning_status,source) VALUES(?,?,?,'new','manual')
                    ON CONFLICT(kind,simplified) DO UPDATE SET traditional=COALESCE(excluded.traditional,entries.traditional),updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                    (kind, simplified, values.get("traditional") or None))
                entry_id = db.execute("SELECT id FROM entries WHERE kind=? AND simplified=?", (kind, simplified)).fetchone()[0]
                self.save_lookup(db, entry_id, values.get("pinyin", ""), values.get("meaning", ""), "manual")
                self.redirect(f"/entry/{entry_id}"); return
            match = re.fullmatch(r"/entry/(\d+)/(status|note|lookup)", path)
            if not match:
                self.respond(page("Not found", "<h1>Page not found</h1>"), 404); return
            entry_id, action = int(match.group(1)), match.group(2)
            exists = db.execute("SELECT 1 FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not exists:
                self.respond(page("Not found", "<h1>Entry not found</h1>"), 404); return
            if action == "status":
                status = values.get("status")
                if status not in STATUSES:
                    self.respond(page("Invalid status", "<p>Unknown learning status.</p>"), 400); return
                db.execute("UPDATE entries SET learning_status=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (status, entry_id))
            elif action == "note":
                body, note_type = values.get("body", ""), values.get("note_type", "general")
                if not body or note_type not in NOTE_TYPES:
                    self.respond(page("Invalid note", "<p>Provide a note and valid note type.</p>"), 400); return
                db.execute("INSERT INTO notes(entry_id,note_type,body) VALUES(?,?,?)", (entry_id, note_type, body))
            elif action == "lookup":
                source = values.get("source") or "manual"
                self.save_lookup(db, entry_id, values.get("pinyin", ""), values.get("meaning", ""), source)
        self.redirect(f"/entry/{entry_id}")

    @staticmethod
    def save_lookup(db, entry_id, pinyin, meaning, source):
        if pinyin:
            db.execute("INSERT OR IGNORE INTO readings(entry_id,pinyin,is_primary,source) VALUES(?,?,0,?)", (entry_id, pinyin, source))
        if meaning:
            db.execute("INSERT OR IGNORE INTO meanings(entry_id,meaning,meaning_order,source) VALUES(?,?,(SELECT COALESCE(MAX(meaning_order),-1)+1 FROM meanings WHERE entry_id=?),?)", (entry_id, meaning, entry_id, source))


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
