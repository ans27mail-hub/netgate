---
title: Keyword Library, translations and the Search Builder
order: 26
updated: v1.0
---
**What it does:** one shared library of search words in categories (Products, Buyer types, Countries and cities, Extra words, …). People pick words to build searches (Search Builder) instead of typing them; each word can have a translation per language. Translations are made once by the local AI, saved, and can be edited and marked checked by a person. Directory keywords can point at library words (`term_ids`) and a language (`lang`), so a German search uses the German words.

## How it works
- `app/keywords.py`: `LANGS` (de, it, fr, es, nl, pl, pt, sv, da, cs, el, tr, ar, ur), `STARTER` categories, `add_terms`, `merge`, `export_csv`/`import_csv`, `translate_missing(term_ids, lang)` (prompt `TRANSLATE_PROMPT`, AI type *discover*), `localize`, `combinations(s, picked, langs)` (max `MAX_COMBOS` = 100), `warnings_for` (reject list, already a keyword, searched in the last 14 days), `record_use`, `accepted_counts`, `starter`.
- `app/web/keyword_routes.py`: `/keywords` (library), categories (save/up/down/delete), terms add/bulk (move, merge, on, off, delete, translate), `/keywords/terms/{id}` (edit, translations, Translate Now), export/import CSV, `/keywords/build` (Search Builder: run now, add as directory keywords, both, use in a request edit).
- `app/jobs.py: search_words(query, term_ids, lang, ctx)`: translates what is missing, then builds the search text in that language. Used by run_job and the night run.
- Directory Settings → Basics: languages of the directory (`groups.langs`); keywords table shows the language and “library”.
- Permission `manage_keywords` (Directories group); anyone who may run requests can pick from the library.

## Data
`kw_categories` (name, position), `kw_terms` (category_id, text, norm, active, notes, uses, found, last_used_at, created_by), `kw_translations` (term_id, lang, text, source ai/person, checked; unique term+lang), `keywords.term_ids` JSON, `keywords.lang`, `groups.langs` JSON.

## Tests
`test_v10.py` (library, add/merge/translate, builder combinations and warnings, run with language, CSV round trip, permission).

## Limits & ideas
Translations are only as good as the local model — mark them checked after a look. More languages are one line in `LANGS`.
