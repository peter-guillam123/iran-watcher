"""Render today's data/YYYY-MM-DD.json to docs/YYYY-MM-DD.html and produce the
homepage as today's brief inline + archive + featured.

All pages link to docs/style.css so the rendered briefs and the hand-written
about/changelog/comparison pages share one design language."""

from __future__ import annotations

import html
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

# Source family display order on the filter row. Sources not listed here are
# appended in count-descending order.
SOURCE_ORDER = [
    "UK Parliament",
    "UK Government",
    "US State Department",
    "US Federal Register",
    "UN Press",
    "IAEA",
    "ReliefWeb",
    "Iran International",
]

FILTER_JS = r"""
(function(){
  var pills = document.querySelectorAll('.pill[data-source]');
  var allPill = document.querySelector('.pill.all');
  var eventsBox = document.querySelector('.events');
  var sortDate = document.querySelector('.sort-pill[data-sort="date"]');
  var sortTier = document.querySelector('.sort-pill[data-sort="tier"]');
  if(!eventsBox) return;
  var originalHTML = eventsBox.innerHTML;

  function activeSources(){
    var s = new Set();
    pills.forEach(function(p){ if(p.dataset.active === '1') s.add(p.dataset.source); });
    return s;
  }
  function applyFilter(){
    var s = activeSources();
    var events = eventsBox.querySelectorAll('.event');
    var headers = eventsBox.querySelectorAll('.tier-header');
    if(s.size === 0){
      events.forEach(function(e){ e.classList.remove('hidden'); });
      headers.forEach(function(h){ h.classList.remove('hidden'); });
      if(allPill) allPill.dataset.active = '1';
    } else {
      if(allPill) allPill.dataset.active = '0';
      events.forEach(function(e){ e.classList.toggle('hidden', !s.has(e.dataset.source)); });
      headers.forEach(function(h){
        var hasVisible = false;
        var n = h.nextElementSibling;
        while(n && !n.classList.contains('tier-header')){
          if(n.classList.contains('event') && !n.classList.contains('hidden')){
            hasVisible = true; break;
          }
          n = n.nextElementSibling;
        }
        h.classList.toggle('hidden', !hasVisible);
      });
    }
  }
  function setActiveSort(btn){
    [sortDate, sortTier].forEach(function(b){
      if(b) b.dataset.active = (b === btn) ? '1' : '0';
    });
  }
  function sortByDate(){
    eventsBox.innerHTML = originalHTML;
    setActiveSort(sortDate);
    applyFilter();
  }
  function sortByTier(){
    eventsBox.innerHTML = originalHTML;
    var events = Array.from(eventsBox.querySelectorAll('.event'));
    var byTier = {};
    events.forEach(function(e){
      var t = e.dataset.tier || '2';
      (byTier[t] = byTier[t] || []).push(e);
    });
    eventsBox.innerHTML = '';
    var labels = {'1':'Tier 1 · clean APIs','2':'Tier 2 · RSS','3':'Tier 3 · scraped / 3rd-party'};
    ['1','2','3'].forEach(function(t){
      var arr = byTier[t];
      if(!arr || arr.length === 0) return;
      var h = document.createElement('h4');
      h.className = 'tier-header t' + t;
      h.textContent = labels[t] || ('Tier ' + t);
      eventsBox.appendChild(h);
      arr.forEach(function(ev){ eventsBox.appendChild(ev); });
    });
    setActiveSort(sortTier);
    applyFilter();
  }
  pills.forEach(function(p){
    p.addEventListener('click', function(){
      p.dataset.active = p.dataset.active === '1' ? '0' : '1';
      applyFilter();
    });
  });
  if(allPill) allPill.addEventListener('click', function(){
    pills.forEach(function(p){ p.dataset.active = '0'; });
    applyFilter();
  });
  if(sortDate) sortDate.addEventListener('click', sortByDate);
  if(sortTier) sortTier.addEventListener('click', sortByTier);
})();
"""


EYE_SVG = (
    '<svg class="eye" viewBox="0 0 40 20" aria-hidden="true" focusable="false">'
    '<path d="M2,10 C8,2 32,2 38,10 C32,18 8,18 2,10 Z" '
    'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>'
    '<circle cx="20" cy="10" r="3.4" fill="currentColor"/>'
    '</svg>'
)


def _masthead() -> str:
    """The wire-service masthead at the top of every page."""
    return (
        '<header class="masthead">'
        f'<a class="wordmark" href="./" aria-label="Iran Watcher home">'
        f'Iran{EYE_SVG}Watcher</a>'
        '<span class="dateline">Daily aggregator · est. 2026</span>'
        '</header>'
    )


def _site_nav(current: str = "") -> str:
    """Top-of-page nav. `current` is the active page key for visual emphasis."""
    items = [
        ("home", "./", "Home"),
        ("comparisons", "comparisons.html", "Comparisons"),
        ("about", "about.html", "About"),
        ("changelog", "changelog.html", "Changelog"),
    ]
    rendered = []
    for key, href, label in items:
        cls = " current" if key == current else ""
        rendered.append(f'<a class="nav-item{cls}" href="{href}">{label}</a>')
    return f'<nav class="site-nav">{"".join(rendered)}</nav>'


def _site_footer() -> str:
    return (
        '<footer class="site">'
        '<span>Iran Watcher · primary-source aggregator for the Iran / Middle East beat</span>'
        '<span><a href="https://github.com/peter-guillam123/iran-watcher" rel="noopener">Source on GitHub</a></span>'
        '</footer>'
    )


def _page(title: str, body: str, *, body_class: str = "", current_nav: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<link rel="stylesheet" href="style.css">
</head><body>
<a class="skip" href="#main">Skip to content</a>
<main class="{body_class}" id="main">
{_masthead()}
{_site_nav(current_nav)}
{body}
{_site_footer()}
</main>
<script>{FILTER_JS}</script>
</body></html>
"""


# Parliament rich layout ---------------------------------------------------

def _party_class(party: str | None) -> str:
    if not party:
        return ""
    p = party.lower()
    if "labour" in p:                    return "lab"
    if "conservative" in p:              return "con"
    if "liberal democrat" in p:          return "ld"
    if "scottish national" in p or "snp" in p: return "snp"
    if "crossbench" in p:                return "xb"
    return ""


def _party_pill(member: dict | None) -> str:
    if not member:
        return ""
    name = html.escape(member.get("name") or "")
    party = member.get("party")
    house = member.get("house")
    cls = _party_class(party)
    house_str = f" · {html.escape(house)}" if house else ""
    party_str = f' <span class="party {cls}">{html.escape(party)}</span>' if party else ""
    return f'<span class="actor">{name}</span>{party_str}{house_str}'


def _render_parliament(e: dict) -> str:
    d = e.get("details") or {}
    asking = d.get("asking_member")
    answering = d.get("answering_member")
    department = d.get("department") or ""
    date_tabled = d.get("date_tabled") or ""
    date_answered = d.get("date_answered") or ""
    question_text = (d.get("question_text") or "").strip()
    answer_text = (d.get("answer_text") or "").strip()
    cat = e.get("category", "")

    if cat == "parliament-statement":
        made_by = d.get("made_by")
        text = (d.get("text") or "").strip()
        meta = (
            f'<div class="meta">'
            f'{_party_pill(made_by) or "<span class=\"actor\">UK Government</span>"}'
            f'<span class="arrow">·</span>{html.escape(department)}'
            f'<span class="arrow">·</span>{html.escape(d.get("date_made") or "")}'
            f'</div>'
        )
        body = (
            f'<div class="qa-block"><div class="qa-label">Statement</div>'
            f'<div class="qa-text">{html.escape(html.unescape(text)) or "(no text)"}</div></div>'
        )
        return f'<div class="parl">{meta}{body}</div>'

    asker_pill = _party_pill(asking) if asking else '<span class="actor">(unknown)</span>'
    answerer_pill = _party_pill(answering)

    meta = (
        f'<div class="meta">'
        f'{asker_pill}'
        f'<span class="arrow">→</span>'
        f'<span>{html.escape(department)}</span>'
        f'<span class="arrow">·</span>'
        f'<span>tabled {html.escape(date_tabled)}</span>'
        f'</div>'
    )

    blocks = []
    if question_text:
        blocks.append(
            f'<div class="qa-block"><div class="qa-label">Question</div>'
            f'<div class="qa-text">{html.escape(html.unescape(question_text))}</div></div>'
        )
    if answer_text:
        ans_label = (
            f'Answer · {html.escape(date_answered)}'
            + (f' · {answerer_pill}' if answerer_pill else "")
        )
        blocks.append(
            f'<div class="qa-block"><div class="qa-label">{ans_label}</div>'
            f'<div class="qa-text">{html.escape(html.unescape(answer_text))}</div></div>'
        )
    body = "".join(blocks)
    return f'<div class="parl">{meta}{body}</div>'


# Event card ---------------------------------------------------------------

def _render_event(e: dict) -> str:
    title = html.escape(html.unescape(e.get("title") or "(untitled)"))
    url = html.escape(e.get("url") or "#")
    source = e.get("source") or "Other"
    source_h = html.escape(source)
    source_detail = html.escape(e.get("source_detail") or "")
    tier = e.get("source_tier") or 2
    cat = e.get("category", "")
    published = (e.get("published_at") or "")[:16].replace("T", " ")
    summary = html.escape(html.unescape(e.get("summary") or ""))
    tags = e.get("tags") or []

    head = (
        f'<div class="head">'
        f'<div class="source-line">'
        f'<span class="tier-mark t{tier}" aria-hidden="true"></span>'
        f'<span class="src">{source_h}</span>'
        + (f' · {source_detail}' if source_detail else "")
        + f'</div>'
        f'<div class="time">{published}Z</div>'
        f'</div>'
        f'<h3><a href="{url}" rel="noopener">{title}</a></h3>'
    )

    if cat.startswith("parliament-"):
        body = _render_parliament(e)
    elif summary:
        body = f'<p class="summary">{summary}</p>'
    else:
        body = ""

    tag_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)

    return (
        f'<article class="event" data-source="{html.escape(source)}" '
        f'data-category="{html.escape(cat)}" data-tier="{tier}">'
        f'{head}{body}'
        + (f'<div class="tags">{tag_html}</div>' if tag_html else "")
        + f'</article>'
    )


# Filter / sort UI ---------------------------------------------------------

def _render_pills(events: list[dict]) -> str:
    if not events:
        return ""
    counts = Counter(e.get("source") or "Other" for e in events)
    ordered = [s for s in SOURCE_ORDER if s in counts]
    extras = sorted([s for s in counts if s not in SOURCE_ORDER], key=lambda s: -counts[s])
    sources = ordered + extras

    filter_pills = [
        f'<button class="pill all" data-active="1" type="button">'
        f'All <span class="n">{len(events)}</span></button>'
    ]
    for s in sources:
        n = counts[s]
        filter_pills.append(
            f'<button class="pill" data-source="{html.escape(s)}" data-active="0" type="button">'
            f'{html.escape(s)} <span class="n">{n}</span></button>'
        )
    sort_pills = (
        '<button class="sort-pill" data-sort="date" data-active="1" type="button">'
        'Date <span class="n">newest first</span></button>'
        '<button class="sort-pill" data-sort="tier" data-active="0" type="button">'
        'Tier <span class="n">1 → 3</span></button>'
    )
    return (
        '<section class="filters" aria-label="Filter and sort">'
        '<div class="filter-row"><h4>Filter by source</h4>'
        + "".join(filter_pills)
        + '</div>'
        '<div class="filter-row sort-row"><h4>Sort by</h4>'
        + sort_pills
        + '</div>'
        '</section>'
    )


# Brief body (shared by dated pages and homepage) --------------------------

def _brief_body(payload: dict, *, include_diagnostics: bool = True) -> str:
    events = payload.get("events", [])
    pills_html = _render_pills(events)
    items_html = "\n".join(_render_event(e) for e in events)
    if not items_html:
        items_html = '<p class="empty">No items matched the Iran/Middle East filter in this window.</p>'

    diag_html = ""
    if include_diagnostics:
        rows = []
        for d in payload.get("diagnostics", []):
            if d.get("ok"):
                rows.append(
                    f'<li><code>{html.escape(d["source"])}</code> — '
                    f'fetched {d["fetched"]}, kept {d["kept"]}</li>'
                )
            else:
                rows.append(
                    f'<li><code>{html.escape(d["source"])}</code> — '
                    f'error: {html.escape((d.get("error") or "")[:200])}</li>'
                )
        if rows:
            diag_html = (
                '<section class="diag" aria-label="Source run diagnostics">'
                '<h4>Source run</h4><ul>' + "".join(rows) + '</ul></section>'
            )

    return f"{pills_html}<section class=\"events\">{items_html}</section>{diag_html}"


# Dated daily brief --------------------------------------------------------

def _pretty_short(stem: str) -> str:
    try:
        return datetime.fromisoformat(stem).strftime("%a %d %b")
    except ValueError:
        return stem


def render_day(
    date_str: str,
    prev_stem: str | None = None,
    next_stem: str | None = None,
) -> str:
    payload = json.loads((DATA_DIR / f"{date_str}.json").read_text())
    events = payload.get("events", [])

    try:
        pretty_date = datetime.fromisoformat(date_str).strftime("%A %d %B %Y")
    except ValueError:
        pretty_date = date_str.replace("-", " ").title()

    window_since = (payload.get("window_since") or "")[:16].replace("T", " ")
    window_until = (payload.get("window_until") or "")[:16].replace("T", " ")
    generated_at = (payload.get("generated_at") or "")[:19].replace("T", " ")

    prev_link = (
        f'<a class="prev" href="{prev_stem}.html">← {_pretty_short(prev_stem)}</a>'
        if prev_stem else '<span class="prev disabled">← earlier</span>'
    )
    next_link = (
        f'<a class="next" href="{next_stem}.html">{_pretty_short(next_stem)} →</a>'
        if next_stem else '<span class="next disabled">later →</span>'
    )

    header = (
        f'<header class="page-header">'
        f'<h1>{html.escape(pretty_date)}</h1>'
        f'<div class="meta">{len(events)} items · '
        f'window {window_since}Z to {window_until}Z · '
        f'generated {generated_at}Z</div>'
        f'</header>'
    )

    nav_top = (
        f'<nav class="day-nav" aria-label="Day navigation">'
        f'{prev_link}<a class="hub" href="./">Archive</a>{next_link}'
        f'</nav>'
    )
    nav_bottom = (
        f'<nav class="day-nav bottom" aria-label="Day navigation">'
        f'{prev_link}<a class="hub" href="./">Archive</a>{next_link}'
        f'</nav>'
    )

    body = header + nav_top + _brief_body(payload) + nav_bottom

    return _page(f"Iran watcher · {pretty_date}", body)


# Homepage = today's brief inline + archive + featured ---------------------

COMPARISONS = [
    {
        "href": "compare-isw-2026-04-24.html",
        "title": "24 April 2026 · the UK angle is loudest here",
        "blurb": (
            "22 items including five UK Parliament Q&amp;As on Arms Trade and "
            "Starmer's IRGC-ban pledge — where the UK-newsroom case is at its "
            "sharpest. State Department and OFAC sanctions on Iran's China oil "
            "network land on the same day."
        ),
    },
    {
        "href": "compare-isw-2026-04-21.html",
        "title": "21 April 2026 · busy day, sanctions match",
        "blurb": (
            "19 of our items vs. ISW's ~8,000-word brief. The Mahan Air "
            "sanctions designation lands on the same day on both sides; Iran "
            "International is unusually rich on regime-domestic-life that ISW "
            "doesn't touch."
        ),
    },
    {
        "href": "compare-isw-2026-04-30.html",
        "title": "30 April 2026 · the original comparison",
        "blurb": (
            "A 48h window matching ISW's 30 April report. 18 items; broader "
            "geopolitical core caught (Strait of Hormuz coalition, Iranian "
            "internal politics, economy collapse), tactical military layer "
            "missed."
        ),
    },
]
DEMO_ENTRY = {
    "href": "last-7-days-demo.html",
    "title": "7-day demo · 54 items across every source",
    "blurb": (
        "A wider window so the filter pills and the Parliament rich layout have "
        "something to demonstrate against. Goes away once the daily cron has "
        "accumulated a few weeks."
    ),
}


def render_home(latest_stem: str | None, dated_days: list[tuple[str, int]]) -> str:
    """The homepage: today's (or most recent) brief shown inline, then
    Featured comparisons, then the full archive."""
    if latest_stem:
        payload = json.loads((DATA_DIR / f"{latest_stem}.json").read_text())
        events = payload.get("events", [])
        try:
            pretty_date = datetime.fromisoformat(latest_stem).strftime("%A %d %B %Y")
        except ValueError:
            pretty_date = latest_stem
        window_since = (payload.get("window_since") or "")[:16].replace("T", " ")
        window_until = (payload.get("window_until") or "")[:16].replace("T", " ")

        intro = (
            f'<header class="page-header">'
            f'<h1>Iran watcher</h1>'
            f'<div class="meta">A daily-updated tip-sheet of primary governmental and multilateral '
            f'sources on Iran and the Middle East crisis. Most recent brief below; '
            f'<a href="about.html">about</a> the project.</div>'
            f'</header>'
            f'<header class="page-header" style="margin-top:32px">'
            f'<h2 style="margin-top:0">{html.escape(pretty_date)}</h2>'
            f'<div class="meta">{len(events)} items · '
            f'window {window_since}Z to {window_until}Z</div>'
            f'</header>'
        )
        brief = _brief_body(payload, include_diagnostics=False)
    else:
        intro = (
            '<header class="page-header">'
            '<h1>Iran watcher</h1>'
            '<div class="meta">A daily-updated tip-sheet of primary governmental and multilateral '
            'sources on Iran and the Middle East crisis.</div>'
            '</header>'
        )
        brief = '<p class="empty">No daily briefs yet — the cron will fill these in.</p>'

    archive_rows = []
    for stem, count in dated_days:
        try:
            pretty = datetime.fromisoformat(stem).strftime("%a %d %b %Y")
        except ValueError:
            continue
        empty_cls = " empty" if count == 0 else ""
        archive_rows.append(
            f'<div class="day{empty_cls}">'
            f'<a href="{stem}.html">{pretty}</a>'
            f'<span class="count">{count} items</span>'
            f'</div>'
        )
    archive = (
        '<section class="archive" aria-label="Daily archive">'
        '<h2>Archive</h2>'
        + ("".join(archive_rows) if archive_rows
           else '<p class="empty">No daily briefs yet.</p>')
        + '</section>'
    )

    body = intro + brief + archive
    return _page("Iran watcher", body, body_class="wide", current_nav="home")


def render_comparisons() -> str:
    """The Comparisons hub: lists each ISW comparison and the demo, with the
    framing that these are evaluation artefacts and not the daily product."""
    cards = []
    for c in COMPARISONS:
        cards.append(
            f'<a class="feat" href="{c["href"]}">'
            f'<div class="feat-title">{c["title"]}</div>'
            f'<div class="feat-blurb">{c["blurb"]}</div>'
            f'</a>'
        )

    body = (
        '<header class="page-header">'
        '<h1>Comparisons</h1>'
        '<div class="meta">Evaluation artefacts. Each comparison reads our '
        'matched-window output for a single day against the ISW Iran Update '
        'covering the same calendar window — so a UK newsroom can see precisely '
        'where this tool overlaps with the ISW product, where it goes silent, '
        'and where it adds something ISW doesn\'t.</div>'
        '</header>'

        '<p>These pages are not part of the daily product. They were written '
        'for an editorial review and will probably retire once the v1 case is '
        'deemed proven. Listed newest first.</p>'

        '<div class="ornament"></div>'

        '<section class="featured" aria-label="ISW comparisons">'
        '<h4>vs. ISW Iran Update</h4>'
        + "".join(cards) +
        '</section>'

        '<section class="featured" aria-label="Demonstration">'
        '<h4>Layout demonstration</h4>'
        f'<a class="feat" href="{DEMO_ENTRY["href"]}">'
        f'<div class="feat-title">{DEMO_ENTRY["title"]}</div>'
        f'<div class="feat-blurb">{DEMO_ENTRY["blurb"]}</div>'
        f'</a>'
        '</section>'
    )
    return _page("Comparisons — Iran & Watcher", body, body_class="wide", current_nav="comparisons")


# Main ---------------------------------------------------------------------

def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    all_stems = [p.stem for p in sorted(DATA_DIR.glob("*.json"))]
    dated = []
    for stem in all_stems:
        try:
            datetime.fromisoformat(stem)
            dated.append(stem)
        except ValueError:
            continue
    prev_of: dict[str, str | None] = {}
    next_of: dict[str, str | None] = {}
    for i, stem in enumerate(dated):
        prev_of[stem] = dated[i - 1] if i > 0 else None
        next_of[stem] = dated[i + 1] if i + 1 < len(dated) else None

    days_for_archive: list[tuple[str, int]] = []
    for stem in reversed(all_stems):
        payload = json.loads((DATA_DIR / f"{stem}.json").read_text())
        count = len(payload.get("events", []))
        out = DOCS_DIR / f"{stem}.html"
        out.write_text(render_day(stem, prev_of.get(stem), next_of.get(stem)))
        days_for_archive.append((stem, count))
        print(f"  wrote {out.name} ({count} items)", file=sys.stderr)

    latest_dated = dated[-1] if dated else None
    (DOCS_DIR / "index.html").write_text(render_home(latest_dated, days_for_archive))
    print(f"  wrote index.html ({len(days_for_archive)} archive entries)", file=sys.stderr)

    (DOCS_DIR / "comparisons.html").write_text(render_comparisons())
    print(f"  wrote comparisons.html", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
