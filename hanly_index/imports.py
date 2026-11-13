"""Import and dictionary-enrichment workflows."""

import csv
import gzip
import json
import re
import urllib.request
from pathlib import Path

from .database import connect

CC_CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CC_CEDICT_LICENSE = "CC BY-SA 4.0"


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
            base = base[:index] + tone_marks[base[index]][tone - 1] + base[index + 1:]
        output.append(base)
    return " ".join(output).lower()


def cedict_entries(path):
    """Yield (traditional, simplified, pinyin, definitions) from CC-CEDICT."""
    pattern = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+/(.*)/$")
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            match = pattern.match(line)
            if not match:
                raise ValueError(f"Could not parse CC-CEDICT line {line_number}: {line[:100]}")
            traditional, simplified, pinyin, raw_definitions = match.groups()
            definitions = [item.strip() for item in raw_definitions.split("/") if item.strip()]
            yield traditional, simplified, pinyin_with_tones(pinyin), definitions


def fetch_cedict(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(CC_CEDICT_URL, headers={"User-Agent": "HanlyIndex/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        with gzip.GzipFile(fileobj=response) as compressed, output.open("wb") as target:
            while chunk := compressed.read(1024 * 1024):
                target.write(chunk)
    return output


def import_csv(file_path, db_path):
    required = {"kind", "simplified"}
    allowed_status = {"new", "learning", "known", "suspended"}
    count = 0
    with Path(file_path).open(newline="", encoding="utf-8-sig") as source, connect(db_path) as db:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV must have at least these columns: kind,simplified")
        for line, row in enumerate(reader, start=2):
            kind = (row.get("kind") or "").strip()
            simplified = (row.get("simplified") or "").strip()
            if kind not in ("character", "word") or not simplified:
                raise ValueError(f"Invalid kind or missing simplified text on CSV line {line}")
            status = (row.get("status") or "new").strip() or "new"
            if status not in allowed_status:
                raise ValueError(f"Invalid status {status!r} on CSV line {line}")
            db.execute(
                """INSERT INTO entries(kind,simplified,traditional,learning_status,source,source_id)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(kind,simplified) DO UPDATE SET
                   traditional=COALESCE(excluded.traditional,entries.traditional),
                   learning_status=excluded.learning_status,
                   source=COALESCE(excluded.source,entries.source),
                   source_id=COALESCE(excluded.source_id,entries.source_id),
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                (kind, simplified, (row.get("traditional") or "").strip() or None, status,
                 (row.get("source") or "").strip() or None, (row.get("source_id") or "").strip() or None),
            )
            entry_id = db.execute("SELECT id FROM entries WHERE kind=? AND simplified=?", (kind, simplified)).fetchone()["id"]
            for pinyin in (row.get("pinyin") or "").split(";"):
                pinyin = pinyin.strip()
                if pinyin:
                    primary = not db.execute("SELECT 1 FROM readings WHERE entry_id=?", (entry_id,)).fetchone()
                    db.execute("INSERT OR IGNORE INTO readings(entry_id,pinyin,is_primary) VALUES(?,?,?)", (entry_id, pinyin, int(primary)))
            for meaning in (row.get("meaning") or "").split(";"):
                meaning = meaning.strip()
                if meaning:
                    db.execute(
                        "INSERT OR IGNORE INTO meanings(entry_id,meaning,meaning_order) VALUES(?,?,(SELECT COALESCE(MAX(meaning_order),-1)+1 FROM meanings WHERE entry_id=?))",
                        (entry_id, meaning, entry_id),
                    )
            count += 1
    return count


def import_hanly(file_path, db_path):
    file_path = Path(file_path)
    source_file = file_path.name
    match = re.search(r"(\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d)", source_file)
    exported_at = (
        f"{match.group(1)[:10]}T{match.group(1)[11:13]}:{match.group(1)[14:16]}:{match.group(1)[17:19]}"
        if match else "unknown"
    )
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Hanly export must be a JSON object keyed by entry text")
    valid = {}
    for key, progress in data.items():
        if not isinstance(key, str) or not isinstance(progress, dict):
            raise ValueError(f"Unexpected Hanly record for key {key!r}")
        percent, status = progress.get("progressPercent"), progress.get("learningStatus")
        if not isinstance(percent, (int, float)) or not 0 <= percent <= 1 or not isinstance(status, str):
            raise ValueError(f"Invalid progress fields for Hanly key {key!r}")
        reverse = key.endswith("_reverse")
        simplified = key[:-8] if reverse else key
        if not simplified:
            raise ValueError(f"Empty entry in Hanly key {key!r}")
        valid[key] = (simplified, "reverse" if reverse else "forward", float(percent), status)

    with connect(db_path) as db:
        batch = db.execute(
            "INSERT INTO learning_progress_exports(source_file,exported_at) VALUES(?,?) ON CONFLICT(source_file) DO NOTHING RETURNING id",
            (source_file, exported_at),
        ).fetchone()
        if batch is None:
            return None
        for source_key, (simplified, direction, percent, status) in valid.items():
            kind = "character" if len(simplified) == 1 else "word"
            db.execute(
                """INSERT INTO entries(kind,simplified,learning_status,source,source_id)
                   VALUES(?,?,'learning','Hanly',?) ON CONFLICT(kind,simplified) DO UPDATE SET
                   source=COALESCE(entries.source,excluded.source),source_id=COALESCE(entries.source_id,excluded.source_id)""",
                (kind, simplified, simplified),
            )
            entry_id = db.execute("SELECT id FROM entries WHERE kind=? AND simplified=?", (kind, simplified)).fetchone()["id"]
            db.execute(
                "INSERT INTO entry_progress(export_id,entry_id,source_key,direction,progress_percent,learning_status) VALUES(?,?,?,?,?,?)",
                (batch["id"], entry_id, source_key, direction, percent, status),
            )
    return len(valid)


def enrich_cedict(file_path, db_path):
    dictionary = {}
    for record in cedict_entries(file_path):
        dictionary.setdefault(record[1], []).append(record)
    matched = set()
    reading_count = meaning_count = 0
    with connect(db_path) as db:
        for entry in db.execute("SELECT id,simplified FROM entries").fetchall():
            records = dictionary.get(entry["simplified"])
            if not records:
                continue
            matched.add(entry["id"])
            for traditional, _simplified, pinyin, definitions in records:
                db.execute("UPDATE entries SET traditional=COALESCE(traditional,?),updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (traditional, entry["id"]))
                before = db.total_changes
                db.execute("INSERT OR IGNORE INTO readings(entry_id,pinyin,is_primary,source,source_license) VALUES(?,?,0,'CC-CEDICT',?)", (entry["id"], pinyin, CC_CEDICT_LICENSE))
                reading_count += db.total_changes - before
                for definition in definitions:
                    before = db.total_changes
                    db.execute(
                        """INSERT OR IGNORE INTO meanings(entry_id,meaning,meaning_order,source,source_license)
                           VALUES(?,?,(SELECT COALESCE(MAX(meaning_order),-1)+1 FROM meanings WHERE entry_id=?),'CC-CEDICT',?)""",
                        (entry["id"], definition, entry["id"], CC_CEDICT_LICENSE),
                    )
                    meaning_count += db.total_changes - before
    return len(matched), reading_count, meaning_count
