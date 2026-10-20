"""Keyword Library and Search Builder (v1.0)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select

from .. import control, methods
from .. import keywords as KW
from ..auth import can, can_any, sees_methods
from ..db import Group, Job, Keyword, KwCategory, KwTerm, SessionLocal
from .common import Forbidden, all_groups, back, can_control, current_user, flash, go, render, require, start_job

router = APIRouter()
USE = ["manage_keywords", "request", "keywords"]   # who may open the library and the Search Builder


def _may_open(user):
    if not can_any(user, USE):
        raise Forbidden


def _manage(user):
    require(user, "manage_keywords")


# ---------- the library ----------

@router.get("/keywords", response_class=HTMLResponse)
def library(request: Request, cat: int = 0, q: str = "", show: str = ""):
    with SessionLocal() as s:
        user = current_user(s, request)
        _may_open(user)
        cats = KW.categories(s)
        sel = next((c for c in cats if c.id == cat), None) if cat else None
        if not sel and not q and cats:
            sel = cats[0]
        if q.strip():
            n = KW.norm(q)
            terms = s.scalars(select(KwTerm).where(KwTerm.norm.contains(n)).order_by(KwTerm.text).limit(300)).all()
        else:
            terms = list(sel.terms) if sel else []
        if show != "off":
            terms = [t for t in terms if t.active] if show == "on" else terms
        acc = KW.accepted_counts(s)
        blocked = {t.id for t in terms if control.rejected_entry(s, t.text, None)}
        return render(request, s, user, "keywords.html", active_nav="keywords", help="keywords", cats=cats, sel=sel,
                      terms=terms, q=q, show=show, acc=acc, blocked=blocked, LANGS=KW.LANGS,
                      may_manage=can(user, "manage_keywords"))


@router.post("/keywords/categories")
async def category_save(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        _manage(user)
        cid = int(form.get("id") or 0) if str(form.get("id") or "").isdigit() else 0
        action = str(form.get("action") or "save")
        cat = s.get(KwCategory, cid) if cid else None
        name = str(form.get("name") or "").strip()[:80]
        if action == "delete" and cat:
            n = len(cat.terms)
            s.delete(cat)
            s.commit()
            flash(request, f"Category “{cat.name}” and its {n} keyword{'s' if n != 1 else ''} deleted. "
                           "Directory keywords made from them stay (as plain keywords).")
            return go("/keywords")
        if action in ("up", "down") and cat:
            cats = KW.categories(s)
            i = cats.index(cat)
            j = i - 1 if action == "up" else i + 1
            if 0 <= j < len(cats):
                cats[i], cats[j] = cats[j], cats[i]
            for pos, c in enumerate(cats):
                c.position = pos
            s.commit()
            return go(f"/keywords?cat={cat.id}")
        if not name:
            flash(request, "Give the category a name.", True)
            return back(request, "/keywords")
        clash = s.scalar(select(KwCategory).where(KwCategory.name == name, KwCategory.id != (cid or 0)))
        if clash:
            flash(request, f"There is already a category called “{name}”.", True)
            return back(request, "/keywords")
        if not cat:
            cat = KwCategory(name=name, position=len(KW.categories(s)))
            s.add(cat)
        cat.name, cat.description = name, str(form.get("description") or "").strip()[:300]
        s.commit()
        flash(request, f"Category “{name}” saved.")
        return go(f"/keywords?cat={cat.id}")


@router.post("/keywords/terms/add")
async def terms_add(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        _manage(user)
        cat = s.get(KwCategory, int(form.get("category_id") or 0))
        if not cat:
            return go("/keywords")
        added, skipped = KW.add_terms(s, cat, KW.split_words(str(form.get("text") or "")), user)
        s.commit()
        flash(request, f"{added} keyword{'s' if added != 1 else ''} added to {cat.name}."
              + (f" Already there: {', '.join(skipped[:5])}." if skipped else ""))
        return go(f"/keywords?cat={cat.id}")


@router.post("/keywords/terms/bulk")
async def terms_bulk(request: Request):
    form = await request.form()
    ids = [int(i) for i in form.getlist("ids") if str(i).isdigit()][:500]
    action = str(form.get("action") or "")
    with SessionLocal() as s:
        user = current_user(s, request)
        _manage(user)
        terms = s.scalars(select(KwTerm).where(KwTerm.id.in_(ids or [-1])).order_by(KwTerm.id)).all()
        if not terms:
            flash(request, "Tick one or more keywords first.", True)
            return back(request, "/keywords")
        if action == "move":
            cat = s.get(KwCategory, int(form.get("to") or 0))
            if not cat:
                flash(request, "Choose the category to move them to.", True)
                return back(request, "/keywords")
            have = {t.norm for t in cat.terms}
            moved = 0
            for t in terms:
                if t.category_id != cat.id and t.norm not in have:
                    t.category_id = cat.id
                    have.add(t.norm)
                    moved += 1
            msg = f"{moved} moved to {cat.name}."
        elif action == "merge":
            if len(terms) < 2:
                flash(request, "Tick at least two keywords to merge.", True)
                return back(request, "/keywords")
            keep = terms[0]
            n = KW.merge(s, keep, terms[1:])
            msg = f"{n} merged into “{keep.text}” (their counts and translations are kept)."
        elif action in ("on", "off"):
            for t in terms:
                t.active = action == "on"
            msg = f"{len(terms)} switched {'on' if action == 'on' else 'off'}."
        elif action == "delete":
            for t in terms:
                s.delete(t)
            msg = f"{len(terms)} deleted. Directory keywords made from them stay (as plain keywords)."
        elif action == "translate":
            lang = str(form.get("lang") or "")
            if lang not in KW.LANGS:
                flash(request, "Choose a language.", True)
                return back(request, "/keywords")
            s.commit()
            n = KW.translate_missing([t.id for t in terms], lang)
            flash(request, f"{n} keyword{'s' if n != 1 else ''} translated into {KW.LANGS[lang]} by your AI and saved"
                  + (" (the others already had a translation or the AI didn't answer)." if n < len(terms) else "."),
                  n == 0 and len(terms) > 0)
            return back(request, "/keywords")
        else:
            return back(request, "/keywords")
        s.commit()
        flash(request, msg)
    return back(request, "/keywords")


@router.get("/keywords/terms/{tid}", response_class=HTMLResponse)
def term_page(request: Request, tid: int):
    with SessionLocal() as s:
        user = current_user(s, request)
        _may_open(user)
        term = s.get(KwTerm, tid)
        if not term:
            return go("/keywords")
        used_in = s.scalars(select(Keyword).where(Keyword.term_ids.contains([tid]))).all()
        jobs = s.scalars(select(Job).where(Job.params["terms"].contains([tid])).order_by(Job.id.desc()).limit(15)).all()
        return render(request, s, user, "keyword_edit.html", active_nav="keywords", help="keywords", term=term,
                      cats=KW.categories(s), LANGS=KW.LANGS, used_in=used_in, jobs=jobs,
                      groups={g.id: g.name for g in all_groups(s)}, may_manage=can(user, "manage_keywords"),
                      acc=KW.accepted_counts(s).get(tid, 0), blocked=control.rejected_entry(s, term.text, None))


@router.post("/keywords/terms/{tid}")
async def term_save(request: Request, tid: int):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        _manage(user)
        term = s.get(KwTerm, tid)
        if not term:
            return go("/keywords")
        if form.get("action") == "translate":
            lang = str(form.get("lang") or "")
            if lang in KW.LANGS:
                tr = KW.translation(term, lang)
                if tr:
                    term.translations.remove(tr)
                    s.commit()
                n = KW.translate_missing([tid], lang)
                flash(request, f"Translated into {KW.LANGS[lang]}." if n else "The AI didn't answer — try again, "
                      "or type the translation yourself.", not n)
            return go(f"/keywords/terms/{tid}")
        text = " ".join(str(form.get("text") or "").split())[:200]
        cat = s.get(KwCategory, int(form.get("category_id") or term.category_id))
        if not text or not cat:
            flash(request, "The keyword can't be empty.", True)
            return go(f"/keywords/terms/{tid}")
        clash = s.scalar(select(KwTerm).where(KwTerm.category_id == cat.id, KwTerm.norm == KW.norm(text),
                                              KwTerm.id != tid))
        if clash:
            flash(request, f"“{text}” is already in {cat.name}. Use Merge to join them.", True)
            return go(f"/keywords/terms/{tid}")
        term.text, term.norm, term.category_id = text, KW.norm(text), cat.id
        term.notes = str(form.get("notes") or "").strip()[:500]
        term.active = form.get("active") == "on"
        for code in KW.LANGS:
            if f"tr_{code}" in form:
                new = str(form.get(f"tr_{code}") or "").strip()
                old = KW.translation(term, code)
                checked = form.get(f"ok_{code}") == "on"
                if old and new == old.text:
                    old.checked = checked
                else:
                    KW.set_translation(term, code, new, source="person", checked=True if new else False)
        s.commit()
        flash(request, "Keyword saved.")
        return go(f"/keywords/terms/{tid}")


@router.get("/keywords/export.csv")
def export(request: Request):
    with SessionLocal() as s:
        user = current_user(s, request)
        _may_open(user)
        data = KW.export_csv(s)
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=netgate-keywords.csv"})


@router.post("/keywords/import")
async def import_(request: Request):
    form = await request.form()
    with SessionLocal() as s:
        user = current_user(s, request)
        _manage(user)
        up = form.get("file")
        raw = (await up.read()).decode("utf-8-sig", "replace") if up and hasattr(up, "read") else ""
        if not raw.strip():
            flash(request, "Choose a CSV file.", True)
            return go("/keywords")
        try:
            added, updated = KW.import_csv(s, raw, user)
        except Exception as e:  # noqa: BLE001
            flash(request, f"Could not read that file: {type(e).__name__}. Use the columns category, keyword, "
                           "active, notes and language codes (de, it …).", True)
            return go("/keywords")
        s.commit()
        flash(request, f"Imported: {added} new keyword{'s' if added != 1 else ''}, {updated} updated.")
    return go("/keywords")


# ---------- the Search Builder ----------

def _picked(params) -> dict:
    out: dict = {}
    for k in params.keys():
        if k.startswith("c_") and k[2:].isdigit():
            ids = [int(x) for x in params.getlist(k) if str(x).isdigit()]
            if ids:
                out[int(k[2:])] = ids
    return out


@router.get("/keywords/build", response_class=HTMLResponse)
def builder(request: Request, group: int = 0, request_id: int = 0):
    with SessionLocal() as s:
        user = current_user(s, request)
        _may_open(user)
        qp = request.query_params
        groups = [g for g in all_groups(s, with_test=can(user, "testing")) if can(user, "request", g.id) or can(user, "manage_dirs")]
        sel = next((g for g in groups if g.id == group), groups[0] if groups else None)
        langs = [x for x in qp.getlist("lang") if x == "" or x in KW.LANGS] if "lang" in qp \
            else ([""] + [x for x in ((sel.langs if sel else []) or []) if x in KW.LANGS])
        picked = _picked(qp)
        combos = []
        if picked and sel:
            combos = KW.combinations(s, picked, langs)
            for c in combos:
                c["warn"] = KW.warnings_for(s, c, sel.id)
        job = s.get(Job, request_id) if request_id else None
        if job and not (can_control(user, job) and control.can_edit(job)):
            job = None
        return render(request, s, user, "builder.html", active_nav="keywords", help="keywords", cats=KW.categories(s),
                      groups=groups, sel=sel, langs=langs, picked=picked, combos=combos, LANGS=KW.LANGS,
                      lang_name=KW.lang_name, job=job, may_run=bool(sel and can(user, "request", sel.id)),
                      may_add=can(user, "manage_dirs"), max_combos=KW.MAX_COMBOS)


@router.post("/keywords/build")
async def builder_go(request: Request):
    form = await request.form()
    action = str(form.get("action") or "")
    chosen = [str(x) for x in form.getlist("combo")]
    with SessionLocal() as s:
        user = current_user(s, request)
        _may_open(user)
        group = s.get(Group, int(form.get("group_id") or 0))
        if not group or not chosen:
            flash(request, "Tick one or more searches first.", True)
            return back(request, "/keywords/build")
        items = []
        for c in chosen:   # "lang|id,id,id"
            lang, _, ids = c.partition("|")
            tids = [int(x) for x in ids.split(",") if x.isdigit()]
            terms = {t.id: t for t in s.scalars(select(KwTerm).where(KwTerm.id.in_(tids or [-1]))).all()}
            if not tids or any(t not in terms for t in tids):
                continue
            items.append({"lang": lang if lang in KW.LANGS else "", "terms": tids,
                          "text": " ".join(terms[t].text for t in tids)})
        if action == "use":   # Edit and Run Again: this one search, in that request
            job = s.get(Job, int(form.get("request_id") or 0))
            if not job or not can_control(user, job) or not items:
                raise Forbidden
            it = items[0]
            if control.rejected_entry(s, it["text"], group.id):
                flash(request, f"“{it['text']}” is on the reject list.", True)
                return back(request, "/requests")
            require(user, "request", group.id)
            use = (job.params or {}).get("methods") if group.id == job.group_id else None
            control.edit_and_run(s, job, user, it["text"], group.id, use, int((job.params or {}).get("deeper") or 0),
                                 terms=it["terms"], lang=it["lang"])
            flash(request, f"Try {len(control.tries(job))} of request #{job.id} started: “{it['text']}”"
                  + (f" in {KW.lang_name(it['lang'])}" if it["lang"] else "") + ".")
            return go("/requests")
        ran = added = skipped = 0
        if action in ("run", "both"):
            require(user, "request", group.id)
            use = methods.enabled_find_methods(group) if sees_methods(user) else None
            for it in items:
                if control.rejected_entry(s, it["text"], group.id):
                    skipped += 1
                    continue
                start_job(s, user, "request", it["text"], group.id,
                          params={"terms": it["terms"], "lang": it["lang"], **({"methods": use} if use else {})})
                ran += 1
        if action in ("add", "both"):
            require(user, "manage_dirs")
            have = {(k.text.lower(), k.lang or "") for k in group.keywords}
            for it in items:
                if (it["text"].lower(), it["lang"]) in have or control.rejected_entry(s, it["text"], group.id):
                    continue
                group.keywords.append(Keyword(text=it["text"][:300], night=True, method="all", found_count=0,
                                              term_ids=it["terms"], lang=it["lang"]))
                have.add((it["text"].lower(), it["lang"]))
                added += 1
            s.commit()
        parts = []
        if ran:
            parts.append(f"{ran} search{'es' if ran != 1 else ''} started — new companies go to the Inbox")
        if added:
            parts.append(f"{added} added to the keywords of {group.name} (they also run at night)")
        if skipped:
            parts.append(f"{skipped} skipped (reject list)")
        flash(request, (". ".join(parts) + ".") if parts else "Nothing new to start or add.", not parts)
    return go(f"/keywords/build?group={group.id}")
