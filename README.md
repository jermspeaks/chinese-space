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
python3 hanly_db.py fetch-cedict
python3 hanly_db.py enrich-cedict data/dictionaries/cedict_ts.u8
```

The database file is intentionally not checked in; back up `hanly.sqlite` and any exports you create.

## Data model

- `entries` stores a simplified headword, optional traditional form, character/word kind, learning status, and source/provenance (for example `Pleco`, `Hanly`, or `manual`). `source_id` can hold an external dictionary identifier.
- `readings` and `meanings` are one-to-many because a character can have multiple pronunciations and senses.
- `notes` stores your own decomposition, mnemonic, usage, or writing notes.
- `components` optionally links a character to component characters when those component entries are in the database.

Pinyin should be stored with tone marks (for example `hǎo`). `fetch-cedict` downloads the current CC-CEDICT text file into the ignored `data/` directory; `enrich-cedict` adds matching pinyin, definitions, traditional forms, and source/license attribution to existing entries. It works locally after download, and unmatched entries are left untouched. Re-run `init` after upgrading an existing database so additive schema migrations are applied.

CC-CEDICT is a free, downloadable dictionary source under CC BY-SA 4.0. Its definitions are useful English glosses, though they are not as detailed as licensed publisher dictionaries and can include several senses. Pleco remains an option for individual lookups or exporting your own flashcards; those exports depend on Pleco's app and the flashcard features available on your platform. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution and license details.

CSV imports require `kind` and `simplified`; other columns are optional. Use semicolons to separate multiple pinyin readings or meanings. Supported columns are `kind`, `simplified`, `traditional`, `pinyin`, `meaning`, `status`, `source`, and `source_id`. Re-importing a row updates its entry and does not duplicate readings or meanings. See [import-template.csv](import-template.csv).

To import a Hanly learning progress JSON export, run `python3 hanly_db.py import-hanly path/to/export.json`. This imports the forward entries as `learning` and preserves each forward/reverse progress record in a dated snapshot. The source export's `progressPercent` is kept as a fraction from 0 to 1; it is not used to infer that an entry is fully known.

## Roadmap

1. **Database foundation (now):** local SQLite schema and commands to add, inspect, and annotate characters and words.
2. **Populate the known set:** the first Hanly export is now imported. Check future exports as your learning progresses; snapshots preserve the progress fields Hanly provides. Deeper review history remains a later optional extension.
3. **Dictionary enrichment:** use CC-CEDICT for broad local coverage, then add Pleco lookups or manually curated notes for entries where its glosses are insufficient.
4. **Reading workflow:** paste/import graded text or articles, segment text into words, compare against known entries, and show unknown or partially known spans. Let you promote selected spans into the database.
5. **Anki export:** generate a reviewable Anki-compatible CSV/package from selected entries, with pinyin, meanings, and your notes. Decomposition can become a card field when you want it.
6. **Later options:** investigate Hanly review-data export and richer review/scheduling fields only after the main vocabulary workflow is working.

The next planned feature is reading analysis: use the dictionary and known-entry set to segment text and surface words that are not yet in your database.
