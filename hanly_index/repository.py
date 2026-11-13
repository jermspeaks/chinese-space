"""Shared SQLite queries and application writes."""


def dashboard_counts(db):
    return {
        "total": db.execute("SELECT count(*) FROM entries").fetchone()[0],
        "characters": db.execute("SELECT count(*) FROM entries WHERE kind='character'").fetchone()[0],
        "words": db.execute("SELECT count(*) FROM entries WHERE kind='word'").fetchone()[0],
        "known": db.execute("SELECT count(*) FROM entries WHERE learning_status='known'").fetchone()[0],
        "coverage": db.execute("SELECT count(DISTINCT entry_id) FROM readings WHERE source='CC-CEDICT'").fetchone()[0],
    }


def search_entries(db, term="", kind="", status="", missing="", offset=0, limit=100):
    where, params = [], []
    if kind in ("character", "word"):
        where.append("e.kind = ?")
        params.append(kind)
    if status in ("new", "learning", "known", "suspended"):
        where.append("e.learning_status = ?")
        params.append(status)
    if term:
        pattern = f"%{term}%"
        where.append("(e.simplified LIKE ? OR e.traditional LIKE ? OR EXISTS (SELECT 1 FROM readings r WHERE r.entry_id=e.id AND r.pinyin LIKE ?) OR EXISTS (SELECT 1 FROM meanings m WHERE m.entry_id=e.id AND m.meaning LIKE ?))")
        params.extend((pattern, pattern, pattern, pattern))
    if missing == "dictionary":
        where.append("NOT EXISTS (SELECT 1 FROM meanings m WHERE m.entry_id=e.id AND m.source='CC-CEDICT')")
    elif missing == "reading":
        where.append("NOT EXISTS (SELECT 1 FROM readings r WHERE r.entry_id=e.id)")
    condition = " WHERE " + " AND ".join(where) if where else ""
    total = db.execute("SELECT count(*) FROM entries e" + condition, params).fetchone()[0]
    rows = db.execute(
        """SELECT e.id,e.kind,e.simplified,e.traditional,e.learning_status,
           (SELECT group_concat(r.pinyin, '; ') FROM readings r WHERE r.entry_id=e.id) pinyin,
           (SELECT group_concat(meaning, '; ') FROM (SELECT m.meaning FROM meanings m WHERE m.entry_id=e.id ORDER BY m.meaning_order LIMIT 2)) meanings,
           (SELECT round(p.progress_percent*100) FROM entry_progress p WHERE p.entry_id=e.id AND p.direction='forward' ORDER BY p.export_id DESC LIMIT 1) forward_progress,
           (SELECT round(p.progress_percent*100) FROM entry_progress p WHERE p.entry_id=e.id AND p.direction='reverse' ORDER BY p.export_id DESC LIMIT 1) reverse_progress
           FROM entries e""" + condition + " ORDER BY e.simplified LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return total, rows


def get_entry_detail(db, entry_id):
    entry = db.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
    if entry is None:
        return None
    return {
        "entry": entry,
        "readings": db.execute("SELECT pinyin,source,source_license FROM readings WHERE entry_id=? ORDER BY is_primary DESC,pinyin", (entry_id,)).fetchall(),
        "meanings": db.execute("SELECT meaning,source,source_license FROM meanings WHERE entry_id=? ORDER BY meaning_order,meaning", (entry_id,)).fetchall(),
        "notes": db.execute("SELECT note_type,body,created_at FROM notes WHERE entry_id=? ORDER BY created_at DESC", (entry_id,)).fetchall(),
        "progress": db.execute("SELECT direction,round(progress_percent*100) percent,learning_status FROM entry_progress WHERE entry_id=? AND export_id=(SELECT max(export_id) FROM entry_progress WHERE entry_id=?) ORDER BY direction", (entry_id, entry_id)).fetchall(),
    }


def character_statuses(db):
    return {row["simplified"]: row["learning_status"] for row in db.execute(
        "SELECT simplified,learning_status FROM entries WHERE kind='character'"
    )}


def save_lookup(db, entry_id, pinyin="", meaning="", source="manual"):
    if pinyin:
        db.execute("INSERT OR IGNORE INTO readings(entry_id,pinyin,is_primary,source) VALUES(?,?,0,?)", (entry_id, pinyin, source))
    if meaning:
        db.execute("INSERT OR IGNORE INTO meanings(entry_id,meaning,meaning_order,source) VALUES(?,?,(SELECT COALESCE(MAX(meaning_order),-1)+1 FROM meanings WHERE entry_id=?),?)", (entry_id, meaning, entry_id, source))


def update_learning_status(db, entry_id, status):
    db.execute("UPDATE entries SET learning_status=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (status, entry_id))


def add_personal_note(db, entry_id, note_type, body):
    db.execute("INSERT INTO notes(entry_id,note_type,body) VALUES(?,?,?)", (entry_id, note_type, body))


def upsert_entry(db, kind, simplified, traditional=None, pinyin="", meaning="", source="manual"):
    db.execute(
        """INSERT INTO entries(kind,simplified,traditional,learning_status,source)
           VALUES(?,?,?,'new',?) ON CONFLICT(kind,simplified) DO UPDATE SET
           traditional=COALESCE(excluded.traditional,entries.traditional),
           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
        (kind, simplified, traditional, source),
    )
    entry_id = db.execute("SELECT id FROM entries WHERE kind=? AND simplified=?", (kind, simplified)).fetchone()[0]
    save_lookup(db, entry_id, pinyin, meaning, source)
    return entry_id


def add_or_update_entry(db, kind, simplified, traditional=None, status="new", source=None, pinyin=None, meaning=None):
    db.execute(
        """INSERT INTO entries(kind,simplified,traditional,learning_status,source)
           VALUES(?,?,?,?,?) ON CONFLICT(kind,simplified) DO UPDATE SET
           traditional=COALESCE(excluded.traditional,entries.traditional),
           learning_status=excluded.learning_status,
           source=COALESCE(excluded.source,entries.source),
           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
        (kind, simplified, traditional, status, source),
    )
    entry_id = db.execute("SELECT id FROM entries WHERE kind=? AND simplified=?", (kind, simplified)).fetchone()[0]
    if pinyin:
        db.execute("INSERT OR IGNORE INTO readings(entry_id,pinyin,is_primary) VALUES(?,?,1)", (entry_id, pinyin))
    if meaning:
        db.execute("INSERT OR IGNORE INTO meanings(entry_id,meaning,meaning_order) VALUES(?,?,(SELECT COALESCE(MAX(meaning_order),-1)+1 FROM meanings WHERE entry_id=?))", (entry_id, meaning, entry_id))
    return entry_id


def find_entry_id(db, simplified):
    row = db.execute("SELECT id FROM entries WHERE simplified=? ORDER BY kind LIMIT 1", (simplified,)).fetchone()
    if row is None:
        raise LookupError(simplified)
    return row["id"]


def list_entry_rows(db, status=None):
    query = "SELECT * FROM entry_summary"
    params = []
    if status:
        query += " WHERE learning_status=?"
        params.append(status)
    return db.execute(query + " ORDER BY simplified", params).fetchall()
