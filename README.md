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
python3 hanly_web.py
```

The local browser UI is available at `http://127.0.0.1:8765`. It provides search and filters, database and dictionary coverage counts, latest Hanly forward/reverse progress, entry details, status updates, personal notes, manual/Pleco lookup entry, and a paste-in reading analyzer. Stop it with Ctrl-C.

The database file is intentionally not checked in; back up `hanly.sqlite` and any exports you create.

## Data model

- `entries` stores a simplified headword, optional traditional form, character/word kind, learning status, and source/provenance (for example `Pleco`, `Hanly`, or `manual`). `source_id` can hold an external dictionary identifier.
- `readings` and `meanings` are one-to-many because a character can have multiple pronunciations and senses.
- `notes` stores your own decomposition, mnemonic, usage, or writing notes.
- `components` optionally links a character to component characters when those component entries are in the database.
- Planned `hsk_vocabulary` and `hsk_character_map` tables will keep standardized vocabulary/levels separate from personal `entries`, with mappings from each HSK word to its character entries.

Pinyin should be stored with tone marks (for example `hǎo`). `fetch-cedict` downloads the current CC-CEDICT text file into the ignored `data/` directory; `enrich-cedict` adds matching pinyin, definitions, traditional forms, and source/license attribution to existing entries. It works locally after download, and unmatched entries are left untouched. Re-run `init` after upgrading an existing database so additive schema migrations are applied.

CC-CEDICT is a free, downloadable dictionary source under CC BY-SA 4.0. Its definitions are useful English glosses, though they are not as detailed as licensed publisher dictionaries and can include several senses. Pleco remains an option for individual lookups or exporting your own flashcards; those exports depend on Pleco's app and the flashcard features available on your platform. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution and license details.

### Character coverage gaps

The current Hanly list has 41 entries without a CC-CEDICT definition: nine CJK Radical Supplement glyphs (`⺀ ⺆ ⺈ ⺌ ⺍ ⺙ ⺤ ⺹ ⻊`), two CJK stroke symbols (`㇑ ㇟`), and 30 other single-character entries (`㐱 㫃 䒑 叚 朩 玨 礻 覀 钅 阝 龰 龶 龷 龸 𠀎 𠂆 𠂇 𠂉 𠂢 𠃓 𠆢 𠕁 𠤕 𠫓 𡗗 𡨄 𡰯 𢀖 𧘇 𰀡`).

Two useful fallbacks were checked against these entries. [Unicode Unihan](https://www.unicode.org/charts/unihan.html) provides an English `kDefinition` for 16 and a Mandarin `kMandarin` reading for 23; [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) provides definitions for 8, with 17 distinct entries covered by at least one source. It also has pinyin and component decomposition fields (a usable decomposition was present for 6 of these entries). These sources do not cover every item: 24 still have no direct definition in either dataset. Some component forms are position-dependent: for example, `阝` can represent left-side 阜 (`fù`) or right-side 邑 (`yì`), so a single global gloss or pronunciation can be misleading. Use Unihan for ordinary and rare ideographs, Make Me a Hanzi for available component/decomposition notes, and handle radical glyphs through canonical radical mappings or a learner dictionary. Stroke symbols should be labeled as stroke forms rather than treated as vocabulary. The downloaded source snapshots are local under ignored `data/dictionaries/` and are not included in Git.

CSV imports require `kind` and `simplified`; other columns are optional. Use semicolons to separate multiple pinyin readings or meanings. Supported columns are `kind`, `simplified`, `traditional`, `pinyin`, `meaning`, `status`, `source`, and `source_id`. Re-importing a row updates its entry and does not duplicate readings or meanings. See [import-template.csv](import-template.csv).

To import a Hanly learning progress JSON export, run `python3 hanly_db.py import-hanly path/to/export.json`. This imports the forward entries as `learning` and preserves each forward/reverse progress record in a dated snapshot. The source export's `progressPercent` is kept as a fraction from 0 to 1; it is not used to infer that an entry is fully known.

## Roadmap

1. **Database foundation (now):** local SQLite schema and commands to add, inspect, and annotate characters and words.
2. **Populate the known set:** the first Hanly export is now imported. Check future exports as your learning progresses; snapshots preserve the progress fields Hanly provides. Deeper review history remains a later optional extension.
3. **Dictionary enrichment:** use CC-CEDICT for broad word coverage, Unihan for additional ideograph readings/glosses, and Make Me a Hanzi for available character decompositions. Resolve radical glyphs through canonical radical mappings and leave stroke symbols as stroke metadata; use Pleco lookups or manual curation for remaining gaps.
4. **Reading workflow:** paste text into the local analyzer to count distinct and repeated characters, compare them with personal character entries and known status, highlight the text, and list missing characters with links to add them. It also suggests possible names using a surname-pattern heuristic for manual review. Next: word segmentation and matching, unknown or partially known word spans, an explicit proper-name review flow, and saved article ingestion/history (the analyzer currently holds submitted text only for the response and does not save it).
5. **Example sentences:** attach example sentences to words and, where useful, senses. Store translation, source, license, and contributor attribution; evaluate [Tatoeba's downloadable sentences](https://tatoeba.org/en/downloads) under its [reuse and attribution guidance](https://en.wiki.tatoeba.org/articles/show/faq), along with manually curated/contextual examples.
6. **HSK reference vocabulary:** add separate, versioned `hsk_vocabulary` and `hsk_character_map` tables for HSK levels 1–9. Keep the standard edition, word, level, source, pinyin, and definitions in the reference vocabulary; map each word to its characters and matching personal entries in the character map. Use it to show level-by-level vocabulary and character coverage without changing personal learning status.
7. **Anki export:** generate a reviewable Anki-compatible CSV/package from selected entries, with pinyin, meanings, examples, and your notes. Decomposition can become a card field when you want it.
8. **Later options:** investigate Hanly review-data export and richer review/scheduling fields only after the main vocabulary workflow is working.

The reading and example-sentence features should share the same word segmentation and vocabulary records, while keeping sentence source and attribution attached to each example.
