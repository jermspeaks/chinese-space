PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('character', 'word')),
    simplified TEXT NOT NULL,
    traditional TEXT,
    learning_status TEXT NOT NULL DEFAULT 'new'
        CHECK (learning_status IN ('new', 'learning', 'known', 'suspended')),
    source TEXT,
    source_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (kind, simplified)
);

CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    pinyin TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    UNIQUE (entry_id, pinyin)
);

CREATE TABLE IF NOT EXISTS meanings (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    meaning TEXT NOT NULL,
    meaning_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    note_type TEXT NOT NULL DEFAULT 'general'
        CHECK (note_type IN ('general', 'decomposition', 'mnemonic', 'usage', 'writing')),
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS components (
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    component_entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    explanation TEXT,
    PRIMARY KEY (entry_id, component_entry_id, position),
    CHECK (entry_id <> component_entry_id)
);

CREATE TABLE IF NOT EXISTS learning_progress_exports (
    id INTEGER PRIMARY KEY,
    source_file TEXT NOT NULL UNIQUE,
    exported_at TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS entry_progress (
    id INTEGER PRIMARY KEY,
    export_id INTEGER NOT NULL REFERENCES learning_progress_exports(id) ON DELETE CASCADE,
    entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('forward', 'reverse')),
    progress_percent REAL NOT NULL CHECK (progress_percent >= 0 AND progress_percent <= 1),
    learning_status TEXT NOT NULL,
    UNIQUE (export_id, source_key)
);

CREATE INDEX IF NOT EXISTS entries_status_idx ON entries(learning_status);
CREATE INDEX IF NOT EXISTS meanings_entry_idx ON meanings(entry_id, meaning_order);
CREATE UNIQUE INDEX IF NOT EXISTS meanings_unique_idx ON meanings(entry_id, meaning);
CREATE INDEX IF NOT EXISTS notes_entry_idx ON notes(entry_id, created_at);
CREATE INDEX IF NOT EXISTS entry_progress_entry_idx ON entry_progress(entry_id, export_id);

CREATE VIEW IF NOT EXISTS entry_summary AS
SELECT e.id, e.kind, e.simplified, e.traditional, e.learning_status, e.source,
       (SELECT group_concat(r.pinyin, '; ') FROM readings r WHERE r.entry_id = e.id) AS pinyin,
       (SELECT group_concat(m.meaning, '; ') FROM meanings m WHERE m.entry_id = e.id) AS meanings,
       e.created_at, e.updated_at
FROM entries e;
