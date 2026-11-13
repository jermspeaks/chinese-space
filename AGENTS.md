# Project guidance

## Purpose

This repository is a local-first Chinese character and vocabulary index for personal study. Its SQLite database is the source of truth. The browser interface binds to `127.0.0.1` and should remain local-only unless the user asks otherwise.

## Data and privacy

- Do not commit the personal SQLite database, Hanly exports, downloaded dictionary snapshots, or other private study data. Keep generated/imported data under ignored `data/` or in the ignored database file.
- Preserve source, license, and attribution details for dictionary entries and example sentences. Consult `THIRD_PARTY_NOTICES.md` before adding datasets.
- Treat pasted reading text as private. Do not persist it unless the user explicitly chooses a saved-article feature.

## Implementation conventions

- Keep the initial app dependency-light and runnable with Python's standard library and SQLite.
- Make schema changes additive where practical and keep initialization/migrations safe to rerun.
- Keep personal learning status separate from reference datasets such as HSK vocabulary.
- Distinguish character-level coverage from word-level coverage. Avoid presenting surname or other proper-name heuristics as definitive; show candidates with context for user review.
- Keep roadmap items in `README.md` and exploratory product/UI ideas in `docs/discovery.md`.

## Useful commands

```sh
python3 hanly_db.py init
python3 hanly_web.py
```

Do not add or run tests unless the user asks for them. For implementation changes, syntax checks such as `python3 -m py_compile hanly_web.py hanly_db.py` are useful.
