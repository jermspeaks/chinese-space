# Hanly character and word index

A personal, local-first vocabulary database for characters and words. SQLite is the initial source of truth: it is portable, easy to back up, and can later feed a reading helper and Anki export without requiring a hosted service.

## Start here

Run `python3 hanly_db.py init` to create `hanly.sqlite` in this directory. Add a character or word with `python3 hanly_db.py add`. Pinyin and meanings can be repeated to record multiple readings and senses. Notes can record decomposition, mnemonics, usage, or writing observations.

```sh
python3 hanly_db.py init
python3 hanly_db.py add character 明 --traditional 明 --pinyin míng --meaning bright --status known
python3 hanly_db.py add word 明天 --traditional 明天 --pinyin míngtiān --meaning tomorrow --status known
python3 hanly_db.py note 明 --type decomposition --text '日 + 月; both parts contribute to the idea of brightness.'
python3 hanly_db.py list --status known
python3 hanly_db.py import-csv your-export.csv
```

The database file is intentionally not checked in; back up `hanly.sqlite` and any exports you create.

## Data model

- `entries` stores a simplified headword, optional traditional form, character/word kind, learning status, and source/provenance (for example `Pleco`, `Hanly`, or `manual`). `source_id` can hold an external dictionary identifier.
- `readings` and `meanings` are one-to-many because a character can have multiple pronunciations and senses.
- `notes` stores your own decomposition, mnemonic, usage, or writing notes.
- `components` optionally links a character to component characters when those component entries are in the database.

Pinyin should be stored with tone marks (for example `hǎo`). Pleco lookups can initially be captured through a manual/export import workflow; automatic lookup depends on what Pleco export or integration access is available. The schema preserves source attribution so imported data can be reviewed and corrected.

CSV imports require `kind` and `simplified`; other columns are optional. Use semicolons to separate multiple pinyin readings or meanings. Supported columns are `kind`, `simplified`, `traditional`, `pinyin`, `meaning`, `status`, `source`, and `source_id`. Re-importing a row updates its entry and does not duplicate readings or meanings. See [import-template.csv](import-template.csv).

To import a Hanly learning progress JSON export, run `python3 hanly_db.py import-hanly path/to/export.json`. This imports the forward entries as `learning` and preserves each forward/reverse progress record in a dated snapshot. The source export's `progressPercent` is kept as a fraction from 0 to 1; it is not used to infer that an entry is fully known.

## Roadmap

1. **Database foundation (now):** local SQLite schema and commands to add, inspect, and annotate characters and words.
2. **Populate the known set:** the first Hanly export is now imported. Check future exports as your learning progresses; snapshots preserve the progress fields Hanly provides. Deeper review history remains a later optional extension.
3. **Pleco-assisted additions:** settle on a reliable lookup path (Pleco export/clipboard first, automation only if supported), then import word, pinyin, and definitions with provenance and duplicate handling.
4. **Reading workflow:** paste/import graded text or articles, segment text into words, compare against known entries, and show unknown or partially known spans. Let you promote selected spans into the database.
5. **Anki export:** generate a reviewable Anki-compatible CSV/package from selected entries, with pinyin, meanings, and your notes. Decomposition can become a card field when you want it.
6. **Later options:** investigate Hanly review-data export and richer review/scheduling fields only after the main vocabulary workflow is working.

The key decision for the next step is what Hanly can export and in what format; that determines how we can import the 2,000+ learned characters with the least manual cleanup.
