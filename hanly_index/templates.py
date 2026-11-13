"""HTML rendering functions for the small local browser UI."""

from html import escape
from urllib.parse import urlencode


def esc(value):
    return escape(str(value or ""), quote=True)


def page(title, content):
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{esc(title)} · Hanly Index</title><link rel='stylesheet' href='/static/style.css'>"
        "<body><header><a href='/'>Hanly Index</a><span class='muted'>Local vocabulary database</span></header>"
        f"<main class='wrap'>{content}</main></body></html>"
    )


def _option(selected, value, label):
    return f"<option value='{esc(value)}' {'selected' if selected == value else ''}>{esc(label)}</option>"


def dashboard(counts, rows, *, term="", kind="", status="", missing="", offset=0, total=0, new_character=""):
    filters = f"""<section class='panel'><form class='filters' method='get'>
    <label>Search<input name='q' value='{esc(term)}' placeholder='Character, word, pinyin, meaning'></label>
    <label>Type<select name='kind'>{_option(kind,'','All types')}{_option(kind,'character','Characters')}{_option(kind,'word','Words')}</select></label>
    <label>Learning status<select name='status'>{_option(status,'','All statuses')}{''.join(_option(status,s,s.title()) for s in ('new','learning','known','suspended'))}</select></label>
    <label>Needs attention<select name='missing'>{_option(missing,'','Any coverage')}{_option(missing,'dictionary','Missing CC-CEDICT definitions')}{_option(missing,'reading','Missing pinyin')}</select></label>
    <button>Filter</button></form></section>"""
    stats = "<section class='stats'>" + "".join(
        f"<div class='stat'><strong>{counts[key]:,}</strong><span>{label}</span></div>"
        for key, label in (("total", "Entries"), ("characters", "Characters"), ("words", "Words"), ("known", "Marked known"), ("coverage", "CC-CEDICT covered"))
    ) + "</section>"
    add_form = f"""<details class='panel' {'open' if new_character else ''}><summary><strong>Add a character or word</strong></summary><form method='post' action='/add' class='filters' style='margin-top:14px'>
    <label>Type<select name='kind'><option value='character'>Character</option><option value='word'>Word</option></select></label>
    <label>Simplified<input name='simplified' value='{esc(new_character)}' required></label><label>Traditional<input name='traditional'></label>
    <label>Pinyin<input name='pinyin' placeholder='nǐ hǎo'></label><label>Meaning<input name='meaning'></label><button>Add entry</button></form></details>"""
    rendered = []
    for row in rows:
        progress = []
        if row["forward_progress"] is not None:
            progress.append(f"Hanly → {row['forward_progress']}%")
        if row["reverse_progress"] is not None:
            progress.append(f"Hanly ← {row['reverse_progress']}%")
        meta = " · ".join(part for part in (row["pinyin"], " / ".join(progress), row["learning_status"]) if part)
        rendered.append(
            f"<a class='entry' href='/entry/{row['id']}'><span class='hanzi'>{esc(row['simplified'])}"
            f"<small class='muted'> {esc(row['traditional'])}</small></span><span><span>{esc(meta)}</span><br>"
            f"<span class='meaning'>{esc(row['meanings'])}</span></span><span><span class='tag'>{esc(row['kind'])}</span></span></a>"
        )

    def page_url(new_offset):
        query = {k: v for k, v in {"q": term, "kind": kind, "status": status, "missing": missing, "offset": new_offset}.items() if v}
        return "/?" + urlencode(query)

    start = min(offset + 1, total) if total else 0
    end = min(offset + len(rows), total)
    pager = f"<div class='pagination'><span>{start}–{end} of {total:,}</span><span>"
    if offset:
        pager += f"<a href='{esc(page_url(max(0, offset - 100)))}'>Previous</a> &nbsp;"
    if offset + 100 < total:
        pager += f"<a href='{esc(page_url(offset + 100))}'>Next</a>"
    pager += "</span></div>"
    content = (
        "<div class='topline'><div><h1>Vocabulary</h1><span class='muted'>Search and review your character and word list.</span></div>"
        "<a class='button secondary' href='/'>Clear filters</a></div>"
        f"{stats}<section class='panel'><h2>Analyze a reading</h2><p>Paste graded text to see character coverage, unfamiliar characters, and possible names.</p>"
        f"<a class='button' href='/article'>Analyze pasted text</a></section>{filters}{add_form}{pager}"
        f"<div class='list'>{''.join(rendered) if rendered else '<div class=\"panel\">No matching entries.</div>'}</div>{pager}"
    )
    return page("Vocabulary", content)


def entry_detail(data):
    entry = data["entry"]
    readings = "".join(
        f"<li>{esc(row['pinyin'])} <span class='muted'>({esc(row['source'] or 'manual')}"
        f"{', ' + esc(row['source_license']) if row['source_license'] else ''})</span></li>"
        for row in data["readings"]
    ) or "<li class='muted'>No pronunciation yet</li>"
    meanings = "".join(
        f"<li>{esc(row['meaning'])} <span class='muted'>({esc(row['source'] or 'manual')}"
        f"{', ' + esc(row['source_license']) if row['source_license'] else ''})</span></li>"
        for row in data["meanings"]
    ) or "<li class='muted'>No meanings yet</li>"
    notes = "".join(
        f"<div class='note'><span class='tag'>{esc(note['note_type'])}</span><div>{esc(note['body'])}</div>"
        f"<small class='muted'>{esc(note['created_at'])}</small></div>" for note in data["notes"]
    ) or "<p class='muted'>No personal notes yet.</p>"
    progress = "".join(
        f"<span class='tag'>Hanly {esc(item['direction'])}: {item['percent']}% · {esc(item['learning_status'])}</span> "
        for item in data["progress"]
    ) or "<span class='muted'>No Hanly progress snapshot</span>"
    status_options = "".join(
        f"<option value='{status}' {'selected' if entry['learning_status'] == status else ''}>{status.title()}</option>"
        for status in ("new", "learning", "known", "suspended")
    )
    content = f"""<p><a href='/'>← All entries</a></p><div class='topline'><div><h1 class='detail-title'>{esc(entry['simplified'])} <small class='muted'>{esc(entry['traditional'])}</small></h1><span class='tag'>{esc(entry['kind'])}</span> <span class='muted'>Source: {esc(entry['source'] or 'manual')}</span></div>
    <form method='post' action='/entry/{entry['id']}/status' class='inline'><label class='field'>Learning status<select name='status'>{status_options}</select></label><button>Save status</button></form></div>
    <section class='panel'><h2>Hanly progress</h2>{progress}</section><div class='detail-grid'>
    <section class='panel'><h2>Pinyin</h2><ul>{readings}</ul><h2>Meanings</h2><ul>{meanings}</ul></section>
    <section class='panel'><h2>Add dictionary lookup</h2><form method='post' action='/entry/{entry['id']}/lookup'><label class='field'>Pinyin<input name='pinyin' placeholder='pinyin with tone marks'></label><label class='field'>Meaning<input name='meaning' placeholder='English gloss'></label><label class='field'>Source<input name='source' value='Pleco'></label><button style='margin-top:10px'>Save lookup</button></form><p class='muted'>This adds a source-attributed reading and/or meaning without replacing existing data.</p></section></div>
    <section class='panel'><h2>Personal notes</h2>{notes}<form method='post' action='/entry/{entry['id']}/note'><div class='filters'><label>Note type<select name='note_type'>{''.join(f'<option value="{t}">{t.title()}</option>' for t in ('general','decomposition','mnemonic','usage','writing'))}</select></label><label class='field' style='flex:3'>Note<textarea name='body' required placeholder='Decomposition, mnemonic, usage, or writing note'></textarea></label><button>Add note</button></div></form></section>"""
    return page(entry["simplified"], content)


def article_form():
    content = """<p><a href='/'>← All entries</a></p><h1>Analyze a reading</h1>
    <section class='panel'><p>Paste an article or graded-reader passage. Text is analyzed in memory and is not saved.</p>
    <form method='post' action='/article'><label class='field'>Chinese text<textarea name='article' required style='min-height:260px' placeholder='Paste Chinese text here'></textarea></label><button style='margin-top:12px'>Analyze text</button></form></section>"""
    return page("Analyze a reading", content)


def article_analysis(result):
    candidates = result["candidates"]
    if candidates:
        candidate_html = "<ul>" + "".join(
            f"<li><span class='tag'>{esc(item['name'])}</span> <span class='muted'>…{esc(item['context'])}…</span></li>"
            for item in candidates
        ) + "</ul>"
    else:
        candidate_html = "<p class='muted'>No likely surname-based name candidates found.</p>"
    unknown_html = "".join(
        f"<a class='tag' href='/?new={esc(item['character'])}'>{esc(item['character'])} × {item['count']}</a> "
        for item in result["unknown"]
    ) or "<p>No characters are missing from your database.</p>"
    highlighted = "".join(
        f"<mark class='{status}'>{esc(text)}</mark>" if status else esc(text)
        for text, status in result["spans"]
    )
    content = f"""<p><a href='/'>← All entries</a> · <a href='/article'>New analysis</a></p><h1>Reading analysis</h1>
    <section class='stats'><div class='stat'><strong>{result['occurrences']:,}</strong><span>Han character occurrences</span></div><div class='stat'><strong>{result['distinct_count']:,}</strong><span>Distinct characters</span></div><div class='stat'><strong>{result['known_occurrences']:,}</strong><span>Occurrences marked known</span></div><div class='stat'><strong>{result['tracked_occurrences']:,}</strong><span>Occurrences in database</span></div><div class='stat'><strong>{len(result['unknown']):,}</strong><span>Distinct characters missing</span></div></section>
    <section class='panel'><h2>Possible proper names</h2>{candidate_html}<p class='muted'>This surname-pattern detector is only a hint and may miss names or flag ordinary words. It does not add candidates to your database.</p></section>
    <section class='panel'><h2>Characters not in your database</h2>{unknown_html}<p class='muted'>Select a character to add it manually. Unknown characters are counted once in the distinct total and by occurrence in the article.</p></section>
    <section class='panel'><h2>Text with character coverage</h2><div style='white-space:pre-wrap;line-height:2;font-size:19px'><mark class='known'>Marked known</mark> <mark class='tracked'>Tracked, not marked known</mark> <mark class='unknown'>Not in database</mark><br><br>{highlighted}</div></section>"""
    return page("Reading analysis", content)
