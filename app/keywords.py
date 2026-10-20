"""Keyword Library and Search Builder (v1.0).

- Categories (Products, Materials, Buyer types, Countries / cities, Extra words …) hold words written in English.
- The Search Builder combines picked words (one from each category) into searches, in chosen languages.
- Translations are made by the local AI the first time a word is needed in a language, then SAVED (marked
  AI-translated) and reused; a person can correct a translation and mark it checked.
- Every search built from library words counts back on those words: times used and companies found
  (accepted is worked out from the Inbox when the library is shown).
"""
import csv
import io
import itertools
import re
from datetime import datetime, timedelta

from sqlalchemy import func, select

from .db import InboxItem, Job, Keyword, KwCategory, KwTerm, KwTranslation, SessionLocal, log

LANGS = {"de": "German", "it": "Italian", "fr": "French", "es": "Spanish", "nl": "Dutch", "pl": "Polish",
         "pt": "Portuguese", "sv": "Swedish", "da": "Danish", "cs": "Czech", "el": "Greek", "tr": "Turkish",
         "ar": "Arabic", "ur": "Urdu"}
LANG_FLAGS = {k: k.upper() for k in LANGS}
MAX_COMBOS = 100
STARTER = [
    ("Products", "What the companies make or sell", ["motorcycle jackets", "leather gloves", "textile suits",
                                                     "riding boots", "protective armour"]),
    ("Buyer types", "Kinds of companies", ["online shop", "distributor", "wholesaler", "brand", "retailer"]),
    ("Countries and cities", "Where to look", ["Germany", "Italy", "France", "United Kingdom", "Netherlands"]),
    ("Extra words", "Words that sharpen a search", ["manufacturer", "wholesale", "private label", "OEM"]),
]


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def lang_name(code: str) -> str:
    return "English" if not code else LANGS.get(code, code.upper())


# ---------- library ----------

def categories(s) -> list:
    return s.scalars(select(KwCategory).order_by(KwCategory.position, KwCategory.name)).all()


def add_terms(s, category, texts, user=None) -> tuple[int, list[str]]:
    """Add words to a category, skipping ones it already has. Returns (added, skipped)."""
    have = {t.norm for t in category.terms}
    added, skipped = 0, []
    for raw in texts:
        txt = re.sub(r"\s+", " ", str(raw or "")).strip()[:200]
        if not txt:
            continue
        n = norm(txt)
        if n in have:
            skipped.append(txt)
            continue
        have.add(n)
        category.terms.append(KwTerm(text=txt, norm=n, active=True, created_by=user.id if user else None))
        added += 1
    return added, skipped


def split_words(text: str) -> list[str]:
    """One word or phrase per line, or separated by commas."""
    return [w.strip() for w in re.split(r"[\n,;]+", text or "") if w.strip()]


def merge(s, keep: KwTerm, others: list) -> int:
    """Merge duplicates into one word: counts are added, translations kept, directory keywords re-linked."""
    n = 0
    have_langs = {t.lang for t in keep.translations}
    for o in others:
        if o.id == keep.id:
            continue
        keep.uses += o.uses or 0
        keep.found += o.found or 0
        if o.last_used_at and (not keep.last_used_at or o.last_used_at > keep.last_used_at):
            keep.last_used_at = o.last_used_at
        for tr in list(o.translations):
            if tr.lang not in have_langs:
                keep.translations.append(KwTranslation(lang=tr.lang, text=tr.text, source=tr.source,
                                                       checked=tr.checked))
                have_langs.add(tr.lang)
        for kw in s.scalars(select(Keyword).where(Keyword.term_ids.contains([o.id]))).all():
            kw.term_ids = list(dict.fromkeys([keep.id if x == o.id else x for x in kw.term_ids]))
        s.delete(o)
        n += 1
    return n


def accepted_counts(s) -> dict:
    """{term id: companies accepted} — Inbox items accepted from searches built with that word."""
    rows = s.execute(select(Job.params, func.count(InboxItem.id)).join(InboxItem, InboxItem.job_id == Job.id)
                     .where(InboxItem.status == "accepted", Job.params.has_key("terms"))  # noqa: W601
                     .group_by(Job.id, Job.params)).all()
    out: dict = {}
    for params, n in rows:
        for tid in (params or {}).get("terms") or []:
            out[tid] = out.get(tid, 0) + n
    return out


def record_use(term_ids: list, found: int):
    """A search built from these words finished: count it on each word."""
    if not term_ids:
        return
    try:
        with SessionLocal() as s:
            for t in s.scalars(select(KwTerm).where(KwTerm.id.in_(list(term_ids)))).all():
                t.uses = (t.uses or 0) + 1
                t.found = (t.found or 0) + max(0, int(found or 0))
                t.last_used_at = datetime.utcnow()
            s.commit()
    except Exception as e:  # noqa: BLE001
        log("warning", "keywords", f"Could not count keyword use: {type(e).__name__}: {e}")


# ---------- CSV ----------

def export_csv(s) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category", "keyword", "active", "notes"] + list(LANGS))
    for c in categories(s):
        for t in c.terms:
            tr = {x.lang: x.text for x in t.translations}
            w.writerow([c.name, t.text, "yes" if t.active else "no", t.notes] + [tr.get(k, "") for k in LANGS])
    return buf.getvalue()


def import_csv(s, text: str, user=None) -> tuple[int, int]:
    """Columns: category, keyword, active (optional), notes (optional), then language codes (de, it …).
    New categories are created; words already there get their notes and translations updated."""
    reader = csv.DictReader(io.StringIO(text))
    cats = {c.name.lower(): c for c in categories(s)}
    added = updated = 0
    for row in reader:
        row = {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}
        cname, word = row.get("category") or "Imported", row.get("keyword") or ""
        if not word:
            continue
        cat = cats.get(cname.lower())
        if not cat:
            cat = KwCategory(name=cname[:80], position=len(cats))
            s.add(cat)
            s.flush()
            cats[cname.lower()] = cat
        term = next((t for t in cat.terms if t.norm == norm(word)), None)
        if term is None:
            term = KwTerm(text=word[:200], norm=norm(word), created_by=user.id if user else None)
            cat.terms.append(term)
            added += 1
        else:
            updated += 1
        if row.get("active"):
            term.active = row["active"].lower() not in ("no", "false", "0", "off")
        if row.get("notes"):
            term.notes = row["notes"][:500]
        for code in LANGS:
            if row.get(code):
                set_translation(term, code, row[code], source="person", checked=True)
    return added, updated


# ---------- translations ----------

def translation(term: KwTerm, lang: str) -> KwTranslation | None:
    return next((t for t in term.translations if t.lang == lang), None)


def set_translation(term: KwTerm, lang: str, text: str, source: str = "person", checked: bool = True):
    tr = translation(term, lang)
    text = re.sub(r"\s+", " ", text or "").strip()[:200]
    if not text:
        if tr:
            term.translations.remove(tr)
        return
    if tr:
        tr.text, tr.source, tr.checked, tr.at = text, source, checked, datetime.utcnow()
    else:
        term.translations.append(KwTranslation(lang=lang, text=text, source=source, checked=checked))


TRANSLATE_PROMPT = """Translate these search keywords from English into {lang}, the way a buyer or trader in that
language would type them into a search engine to find companies (trade words, not literal word-for-word).
Keep names of places in their usual {lang} form. Keep brand names and abbreviations like OEM as they are.
Return JSON only: {{"translations": {{"<english>": "<{lang}>", ...}}}}
Keywords:
{words}"""


def translate_missing(term_ids: list, lang: str) -> int:
    """Translate the words that have no saved translation in `lang`, with the local AI, and save them.
    Returns how many were translated. Never raises."""
    if not lang or lang not in LANGS or not term_ids:
        return 0
    from . import ai
    try:
        with SessionLocal() as s:
            terms = [t for t in s.scalars(select(KwTerm).where(KwTerm.id.in_(list(term_ids)))).all()
                     if not translation(t, lang)]
            if not terms:
                return 0
            data = ai.ask_json("discover", TRANSLATE_PROMPT.format(lang=LANGS[lang],
                                                                  words="\n".join(f"- {t.text}" for t in terms)))
            got = (data or {}).get("translations") or {}
            low = {str(k).strip().lower(): v for k, v in got.items()} if isinstance(got, dict) else {}
            n = 0
            for t in terms:
                v = low.get(t.text.lower()) or low.get(t.norm)
                if isinstance(v, str) and v.strip():
                    set_translation(t, lang, v, source="ai", checked=False)
                    n += 1
            s.commit()
            return n
    except Exception as e:  # noqa: BLE001
        log("warning", "keywords", f"Could not translate keywords into {lang}: {type(e).__name__}: {e}")
        return 0


def localize(s, term_ids: list, lang: str, english: str) -> str:
    """The search text for these words in `lang` (saved translations; English for a word not translated yet)."""
    if not lang or not term_ids:
        return english
    by_id = {t.id: t for t in s.scalars(select(KwTerm).where(KwTerm.id.in_(list(term_ids)))).all()}
    parts = []
    for tid in term_ids:
        t = by_id.get(tid)
        if t:
            tr = translation(t, lang)
            parts.append(tr.text if tr else t.text)
    return " ".join(parts) or english


# ---------- Search Builder ----------

def combinations(s, picked: dict, langs: list[str]) -> list[dict]:
    """picked = {category id: [term ids]} → every combination (one word per category, in category order),
    for each language. [{text (English), terms [ids], lang, search (the words in that language, if known)}]"""
    cats = [c for c in categories(s) if picked.get(c.id)]
    lists = []
    for c in cats:
        ids = set(picked[c.id])
        terms = [t for t in c.terms if t.id in ids and t.active]
        if terms:
            lists.append(terms)
    out = []
    for combo in itertools.product(*lists) if lists else []:
        english = " ".join(t.text for t in combo)
        ids = [t.id for t in combo]
        for lang in (langs or [""]):
            missing = [t.text for t in combo if lang and not translation(t, lang)]
            search = " ".join((translation(t, lang).text if lang and translation(t, lang) else t.text) for t in combo)
            out.append({"text": english, "terms": ids, "lang": lang, "search": search, "missing": missing})
            if len(out) >= MAX_COMBOS:
                return out
    return out


def warnings_for(s, combo: dict, group_id: int) -> list[str]:
    """Reject list, already a keyword of the directory, searched in the last 14 days."""
    from .control import norm_keyword, rejected_entry
    out = []
    if rejected_entry(s, combo["text"], group_id) or (combo["lang"] and rejected_entry(s, combo["search"], group_id)):
        out.append("on the reject list")
    if s.scalar(select(Keyword.id).where(Keyword.group_id == group_id, func.lower(Keyword.text) == combo["text"].lower(),
                                         Keyword.lang == (combo["lang"] or "")).limit(1)):
        out.append("already a keyword here")
    since = datetime.utcnow() - timedelta(days=14)
    n = norm_keyword(combo["text"])
    for q, params in s.execute(select(Job.query, Job.params).where(Job.group_id == group_id, Job.created_at >= since,
                                                                   Job.kind.in_(["request", "keyword"]))).all():
        if norm_keyword(q) == n and ((params or {}).get("lang") or "") == (combo["lang"] or ""):
            out.append("searched in the last 14 days")
            break
    return out


def starter(s):
    """First time: a few example categories and words, plus the directories' own keywords."""
    if s.scalar(select(func.count(KwCategory.id))):
        return
    for i, (name, desc, words) in enumerate(STARTER):
        c = KwCategory(name=name, description=desc, position=i)
        s.add(c)
        add_terms(s, c, words)
    texts = sorted({k.text.strip() for k in s.scalars(select(Keyword)).all() if k.text.strip()}, key=str.lower)
    if texts:
        c = KwCategory(name="From directories", description="The keywords your directories had before v1.0",
                       position=len(STARTER))
        s.add(c)
        add_terms(s, c, texts)
        s.flush()
        by_norm = {t.norm: t.id for t in c.terms}
        for k in s.scalars(select(Keyword)).all():
            if not k.term_ids and norm(k.text) in by_norm:
                k.term_ids = [by_norm[norm(k.text)]]
