# Roadmap

This document tracks capabilities still to develop. Current usability observations and product ideas also live in [docs/discovery.md](docs/discovery.md).

## In progress

- **Reading analysis:** extend the paste-in character coverage view with Chinese word segmentation, word-level known/learning/new status, unknown-word highlighting, and a review flow to add selected words to the personal database. The current analyzer compares characters and does not save pasted text.
- **Name handling:** improve the current surname-pattern hints with an explicit review/ignore action and context-aware classification. Keep names optional so they do not inflate vocabulary learning counts.
- **Character display:** investigate fallback fonts for radicals and stroke forms such as `㇑` and `㇟`; identify affected glyphs and choose fonts that render them reliably across common systems.

## Planned

- **Reader mode:** show sentence boundaries and let the reader open a sentence for a focused view with pinyin, translation, and word-by-word familiarity/coverage. Support translating or annotating sentences as data becomes available.
- **Radical metadata:** allow entries to be tagged as radicals/components, capture variant and positional forms, and distinguish radical/stroke metadata from ordinary vocabulary.
- **Article ingestion:** add saved article records, titles/source metadata, and analysis history after the paste-only workflow is useful. Keep article text private and local by default.
- **Example sentences:** attach example sentences to words and, where useful, senses, including translation and source/license/contributor attribution. Evaluate [Tatoeba downloads](https://tatoeba.org/en/downloads) under its [reuse and attribution guidance](https://en.wiki.tatoeba.org/articles/show/faq), alongside manually curated examples.
- **HSK 1–9 reference vocabulary:** create separate, versioned `hsk_vocabulary` and `hsk_character_map` tables. Track standard edition, level, word, source, pinyin, and definitions; map each HSK word to its constituent characters and personal entries. Show level-by-level coverage without changing personal learning status.
- **Anki export:** produce a reviewable Anki-compatible CSV/package for selected entries with character/word, pinyin, meanings, examples, and personal notes; decomposition can be included as a card field.
- **Hanly review history:** investigate whether Hanly can export review events or scheduling data, then decide whether deeper review history is useful to store.

## Later / research

- Improve dictionary coverage for rare ideographs and radical forms using Unihan, Make Me a Hanzi, canonical radical mappings, Pleco/manual curation, and properly attributed sources. Keep stroke symbols labeled as stroke metadata.
- Revisit article segmentation and dictionary source choices if the initial lightweight implementation needs more language tooling.

The reading, reader-mode, and example-sentence features should share word segmentation and vocabulary records. Keep source and license attribution attached to imported or curated examples.
