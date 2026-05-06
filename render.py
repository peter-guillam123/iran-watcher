"""Render today's data/YYYY-MM-DD.json to docs/YYYY-MM-DD.html and produce the
homepage as today's brief inline + archive + featured.

All pages link to docs/style.css so the rendered briefs and the hand-written
about/changelog/comparison pages share one design language."""

from __future__ import annotations

import html
import json
import re
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
    "CENTCOM",
    "IDF",
    "UN Press",
    "IAEA",
    "ReliefWeb",
    "Times of Israel",
    "Jerusalem Post",
    "Iran International",
    "Regime channels",
]

RELATIVE_TIME_JS = r"""
(function(){
  var els = document.querySelectorAll('.last-updated[data-generated-at]');
  if(!els.length) return;
  function fmt(generated){
    var ms = Date.now() - generated.getTime();
    if(ms < 0) return 'just now';
    var mins = Math.floor(ms / 60000);
    if(mins < 1) return 'just now';
    if(mins === 1) return '1 minute ago';
    if(mins < 60) return mins + ' minutes ago';
    var hours = Math.floor(mins / 60);
    if(hours === 1) return '1 hour ago';
    if(hours < 24) return hours + ' hours ago';
    var days = Math.floor(hours / 24);
    if(days === 1) return '1 day ago';
    if(days < 14) return days + ' days ago';
    var weeks = Math.floor(days / 7);
    return weeks + ' weeks ago';
  }
  function update(){
    els.forEach(function(el){
      var iso = el.dataset.generatedAt;
      if(!iso) return;
      var d = new Date(iso);
      if(isNaN(d.getTime())) return;
      el.textContent = fmt(d);
      el.title = iso;
    });
  }
  update();
  setInterval(update, 60000);  /* refresh once a minute while page is open */
})();
"""

FILTER_JS = r"""
(function(){
  var pills = document.querySelectorAll('.pill[data-source]');
  var allPill = document.querySelector('.pill.all');
  var eventsBox = document.querySelector('.events');
  var sortDate = document.querySelector('.sort-pill[data-sort="date"]');
  var sortTier = document.querySelector('.sort-pill[data-sort="tier"]');
  var refineFigures = document.querySelector('.refine-pill[data-refine="figures"]');
  var refinePrimary = document.querySelector('.refine-pill[data-refine="primary"]');
  var threadBtns = document.querySelectorAll('.thread-btn[data-thread-ids]');
  if(!eventsBox) return;
  var originalHTML = eventsBox.innerHTML;
  var activeThreadIds = null;  // Set of event ids when a thread is active

  function activeSources(){
    var s = new Set();
    pills.forEach(function(p){ if(p.dataset.active === '1') s.add(p.dataset.source); });
    return s;
  }
  function figuresOnly(){
    return refineFigures && refineFigures.dataset.active === '1';
  }
  function primaryOnly(){
    return refinePrimary && refinePrimary.dataset.active === '1';
  }
  function shouldShow(e, sources){
    // All filters compose: source AND primary-only AND figures-only AND thread.
    if(sources.size > 0 && !sources.has(e.dataset.source)) return false;
    if(figuresOnly() && e.dataset.figures !== '1') return false;
    if(primaryOnly()){
      var t = parseInt(e.dataset.tier || '2', 10);
      if(t > 2) return false;
    }
    if(activeThreadIds){
      // Cluster wrappers carry data-child-ids; show the cluster if any of
      // its children are cited by the active thread.
      if(e.classList.contains('channel-cluster')){
        var childIds = (e.dataset.childIds || '').split('|').filter(Boolean);
        var anyMatch = childIds.some(function(id){ return activeThreadIds.has(id); });
        if(!anyMatch) return false;
      } else {
        if(!activeThreadIds.has(e.dataset.id)) return false;
      }
    }
    return true;
  }
  function applyFilter(){
    var s = activeSources();
    var events = eventsBox.querySelectorAll('.event');
    var headers = eventsBox.querySelectorAll('.tier-header');
    var allActive = (s.size === 0);
    if(allPill) allPill.dataset.active = allActive ? '1' : '0';
    events.forEach(function(e){
      e.classList.toggle('hidden', !shouldShow(e, s));
    });
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
    // Only iterate top-level events — never tear cluster children out of
    // their .cluster-body wrapper (they belong inside the expander).
    var topLevel = Array.from(eventsBox.querySelectorAll(':scope > .event'));
    var broadcastZone = eventsBox.querySelector(':scope > .broadcast-zone');
    var clusterWrappers = broadcastZone
      ? Array.from(broadcastZone.querySelectorAll('.event.channel-cluster'))
      : [];
    var allTopLevel = topLevel.concat(clusterWrappers);
    var byTier = {};
    allTopLevel.forEach(function(e){
      var t = e.dataset.tier || '2';
      (byTier[t] = byTier[t] || []).push(e);
    });
    eventsBox.innerHTML = '';
    var labels = {'1':'Tier 1 · clean APIs','2':'Tier 2 · RSS','3':'Tier 3 · scraped / 3rd-party','4':'Tier 4 · channel claim, unverified'};
    ['1','2','3','4'].forEach(function(t){
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
    rebindClusterToggles();
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
  if(sortDate) sortDate.addEventListener('click', function(){
    sortByDate();
    rebindClusterToggles();
  });
  if(sortTier) sortTier.addEventListener('click', sortByTier);
  if(refineFigures) refineFigures.addEventListener('click', function(){
    refineFigures.dataset.active = refineFigures.dataset.active === '1' ? '0' : '1';
    applyFilter();
  });
  if(refinePrimary) refinePrimary.addEventListener('click', function(){
    refinePrimary.dataset.active = refinePrimary.dataset.active === '1' ? '0' : '1';
    applyFilter();
  });

  // Clickable threads — each click toggles a "filter to just this thread's
  // events" mode. Clicking the same thread again clears it. Clicking a
  // different thread switches the filter without an extra click.
  function setActiveThread(btn){
    threadBtns.forEach(function(b){
      var on = (b === btn);
      b.dataset.active = on ? '1' : '0';
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if(btn){
      var ids = (btn.dataset.threadIds || '').split('|').filter(Boolean);
      activeThreadIds = new Set(ids);
    } else {
      activeThreadIds = null;
    }
    applyFilter();
  }
  threadBtns.forEach(function(btn){
    btn.addEventListener('click', function(){
      var alreadyActive = btn.dataset.active === '1';
      setActiveThread(alreadyActive ? null : btn);
    });
  });

  // Cluster expand/collapse — applied to current toggles in the DOM. Must
  // be re-bound after sort operations rebuild the events container.
  function rebindClusterToggles(){
    document.querySelectorAll('.cluster-toggle').forEach(function(btn){
      if(btn.dataset.bound === '1') return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', function(){
        var cluster = btn.closest('.channel-cluster');
        if(!cluster) return;
        var body = cluster.querySelector('.cluster-body');
        if(!body) return;
        var open = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', open ? 'false' : 'true');
        if(open){
          body.setAttribute('hidden', '');
        } else {
          body.removeAttribute('hidden');
        }
      });
    });
  }
  rebindClusterToggles();
})();
"""


def _masthead() -> str:
    """The wire-service masthead at the top of every page."""
    return (
        '<header class="masthead">'
        '<a class="wordmark" href="./">Iran Watcher</a>'
        '<span class="dateline">Daily aggregator · est. 2026</span>'
        '</header>'
    )


def _site_nav(current: str = "") -> str:
    """Top-of-page nav. `current` is the active page key for visual emphasis."""
    items = [
        ("home", "./", "Home"),
        ("archive", "archive.html", "Archive"),
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


DEFAULT_DESCRIPTION = (
    "Primary-source aggregator for the Iran & Middle East beat — "
    "what governments and multilateral bodies actually said today."
)


def _page(
    title: str,
    body: str,
    *,
    body_class: str = "",
    current_nav: str = "",
    description: str = DEFAULT_DESCRIPTION,
) -> str:
    desc = html.escape(description)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="description" content="{desc}">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="alternate icon" href="favicon.svg">
<link rel="stylesheet" href="style.css">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:image" content="og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="og-image.png">
</head><body>
<a class="skip" href="#main">Skip to content</a>
<main class="{body_class}" id="main">
{_masthead()}
{_site_nav(current_nav)}
{body}
{_site_footer()}
</main>
<script>{RELATIVE_TIME_JS}{FILTER_JS}</script>
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

_TRAILING_ELLIPSIS_RE = re.compile(r"[…\.…]+$")
_WS_RE = re.compile(r"\s+")

# Language code → display name. Used to label "Translated · Persian" badges
# on cards where Claude translated the title/summary from the original.
_LANG_NAMES = {
    "fa": "Persian",
    "ar": "Arabic",
    "he": "Hebrew",
    "ku": "Kurdish",
    "tr": "Turkish",
    "ru": "Russian",
}


def _translated_badge_html(event: dict) -> str:
    """Small badge marking a card as auto-translated, with the source
    language named. Visible in the head row regardless of whether the
    summary survived the title/summary dedup pass.

    Returns empty string if the event isn't translated."""
    if not event.get("title_en"):
        return ""
    lang_code = (event.get("details") or {}).get("language") or ""
    lang_name = _LANG_NAMES.get(lang_code.lower(), "")
    label = f"Translated · {lang_name}" if lang_name else "Translated"
    tooltip = (
        f"Auto-translated from {lang_name} by Claude. "
        if lang_name
        else "Auto-translated by Claude. "
    ) + "Click the headline link for the original."
    return (
        f'<span class="translated-badge" title="{html.escape(tooltip)}">'
        f'{html.escape(label)}'
        '</span>'
    )


def _normalise_for_compare(s: str) -> str:
    """Lower-case, strip, collapse whitespace, drop trailing ellipsis. Used
    for detecting near-duplicate title/summary pairs from sources where the
    title is just the first chunk of the body (Twitter, Bluesky, sometimes
    Telegram)."""
    s = (s or "").strip()
    s = _TRAILING_ELLIPSIS_RE.sub("", s)
    s = _WS_RE.sub(" ", s)
    return s.lower()


def _summary_redundant(title: str, summary: str) -> bool:
    """True if `summary` is a near-superset of `title` and adds nothing
    substantive beyond it.

    The simplest rule that works: if normalised summary starts with
    normalised title, the summary is redundant. The title was synthesised
    from the first chunk of the body anyway, so anything past it is either
    attribution boilerplate (— @IDF May 3, 2026) or trailing content that's
    one click away on the original source.
    """
    if not title or not summary:
        return False
    nt = _normalise_for_compare(title)
    ns = _normalise_for_compare(summary)
    if not nt or not ns:
        return False
    if ns == nt:
        return True
    if ns.startswith(nt):
        return True
    # Inverse case: title is a superset of summary (rare, but possible
    # when an adapter packs more into the title than the summary).
    if nt.startswith(ns):
        return True
    return False


def _render_event(e: dict) -> str:
    # Prefer English translations when present (Telegram channels are
    # collected in their original Persian/Arabic; the translate pass
    # writes back title_en / summary_en).
    title_en = e.get("title_en")
    summary_en = e.get("summary_en")
    raw_title = title_en or e.get("title") or "(untitled)"
    raw_summary = summary_en or e.get("summary") or ""

    # Suppress redundant summaries — for Twitter/X and Bluesky cards (and
    # some Telegram posts), the title is synthesised from the first ~140
    # chars of the body and the summary is the same body, so the summary
    # adds no editorial value above what the headline already conveys. If
    # the normalised summary starts with the normalised title, we drop it.
    if raw_summary and _summary_redundant(raw_title, raw_summary):
        raw_summary = ""

    title = html.escape(html.unescape(raw_title))
    url = html.escape(e.get("url") or "#")
    source = e.get("source") or "Other"
    source_h = html.escape(source)
    source_detail = html.escape(e.get("source_detail") or "")
    tier = e.get("source_tier") or 2
    cat = e.get("category", "")
    published = (e.get("published_at") or "")[:16].replace("T", " ")
    summary = html.escape(html.unescape(raw_summary))
    is_translated = bool(title_en)
    tags = e.get("tags") or []

    detail_html = (
        f'<div class="src-detail">{source_detail}</div>' if source_detail else ""
    )
    translated_html = _translated_badge_html(e)
    head = (
        f'<div class="head">'
        f'<div class="source-info">'
        f'<div class="src-row">'
        f'<span class="tier-mark t{tier}" aria-hidden="true"></span>'
        f'<span class="src">{source_h}</span>'
        f'{translated_html}'
        f'</div>'
        f'{detail_html}'
        f'</div>'
        f'<div class="time">{published}Z</div>'
        f'</div>'
        f'<h3><a href="{url}" rel="noopener">{title}</a></h3>'
    )

    if cat.startswith("parliament-"):
        body = _render_parliament(e)
    elif summary:
        # Translation marker is in the head row now (via translated_html)
        # so the reader sees it even when the summary is dropped.
        body = f'<p class="summary">{summary}</p>'
    else:
        body = ""

    tag_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)

    has_figures = bool(e.get("has_figures"))
    fig_marker = ""
    if has_figures:
        examples = e.get("figures_examples") or []
        tooltip = (
            "Specific figures cited: " + ", ".join(examples)
            if examples
            else "Specific figures cited"
        )
        fig_marker = (
            f'<span class="fig-marker" title="{html.escape(tooltip)}">'
            f'<span class="fig-mark-dot" aria-hidden="true">●</span>'
            f'<span class="fig-mark-label">fig.</span>'
            f'</span>'
        )

    head_with_marker = head.replace(
        '</h3>', f'{fig_marker}</h3>', 1
    ) if fig_marker else head

    event_id = e.get("id") or ""
    return (
        f'<article class="event" data-source="{html.escape(source)}" '
        f'data-category="{html.escape(cat)}" data-tier="{tier}" '
        f'data-figures="{1 if has_figures else 0}" '
        f'data-id="{html.escape(event_id)}">'
        f'{head_with_marker}{body}'
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
        'Tier <span class="n">primary first</span></button>'
    )

    n_with_figs = sum(1 for e in events if e.get("has_figures"))
    n_primary = sum(1 for e in events if (e.get("source_tier") or 2) <= 2)
    refine_pills = (
        '<button class="sort-pill refine-pill" data-refine="primary" data-active="0" type="button" '
        'title="Show only tier 1+2 — primary governmental, multilateral, official-body broadcasts. Hides Iran International and regime-channel claims.">'
        f'Primary sources only <span class="n">{n_primary}</span></button>'
        '<button class="sort-pill refine-pill" data-refine="figures" data-active="0" type="button" '
        'title="Show only items citing specific figures — strikes, sanctions amounts, vessel counts, etc.">'
        f'With figures only <span class="n">{n_with_figs}</span></button>'
    )

    return (
        '<section class="filters" aria-label="Filter and sort">'
        '<div class="filter-row"><h4>Filter by source</h4>'
        + "".join(filter_pills)
        + '</div>'
        '<div class="filter-row sort-row"><h4>Sort by</h4>'
        + sort_pills
        + '</div>'
        '<div class="filter-row refine-row"><h4>Refine</h4>'
        + refine_pills
        + '</div>'
        '</section>'
    )


# Brief body (shared by dated pages and homepage) --------------------------

def _brief_body(payload: dict, *, include_diagnostics: bool = True) -> str:
    events = payload.get("events", [])
    day_shape_html = _render_day_shape(payload.get("day_shape") or "", len(events))
    threads_html = _render_threads(payload.get("threads") or [])
    pills_html = _render_pills(events)
    items_html = _render_events_with_clusters(events)
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

    return f"{day_shape_html}{threads_html}{pills_html}<section class=\"events\">{items_html}</section>{diag_html}"


def _render_events_with_clusters(events: list[dict]) -> str:
    """Render events with two structural zones: a documents zone above and a
    broadcast zone below.

    Editorially these are different units. UK Parliament Q&A, Federal
    Register designations, State Dept press releases, gov.uk Atom items,
    Iran International articles, Times of Israel and Jerusalem Post
    headlines — all *documents* with publication weight. IDF and CENTCOM
    tweets, Khamenei / IRIB / Defa Press posts — all short *broadcasts*
    from a single official source.

    The broadcast zone holds two visually-distinguished sub-blocks:
      · Military broadcasts (tier 2, ink rule)        — IDF, CENTCOM
      · Regime channels      (tier 4, accent rule)    — Telegram channels

    Both use the same compaction mechanism: one collapsible cluster per
    handle, latest item as a teaser, expand to read all posts. The visual
    signal still distinguishes "this is what they said" from "this is a
    one-sided regime claim".
    """
    # Bluesky and X-via-rss.app handles we treat as broadcast clusters
    # rather than inline cards. Bluesky is excluded — Times of Israel and
    # Jerusalem Post are newspapers, not broadcasts.
    MILITARY_SOURCES = {"IDF", "CENTCOM"}

    document_events: list[dict] = []
    military: dict[str, list[dict]] = {}        # source -> events
    regime: dict[str, list[dict]] = {}          # channel handle -> events

    for e in events:
        details = e.get("details") or {}
        src = e.get("source") or ""
        if src == "Regime channels" and details.get("channel_handle"):
            regime.setdefault(details["channel_handle"], []).append(e)
        elif src in MILITARY_SOURCES:
            military.setdefault(src, []).append(e)
        else:
            document_events.append(e)

    parts = [_render_event(e) for e in document_events]

    if military or regime:
        sub_blocks: list[str] = []

        if military:
            mil_clusters = [
                _render_broadcast_cluster(
                    handle=src,
                    items=items,
                    kind="military",
                    tier=2,
                    source_for_filter=src,  # "IDF" / "CENTCOM" matches source pill
                )
                for src, items in sorted(military.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            ]
            sub_blocks.append(
                '<div class="broadcast-sub broadcast-sub-military">'
                '<h5 class="broadcast-sub-caption">Military spokes · official-body broadcasts</h5>'
                + "".join(mil_clusters)
                + '</div>'
            )

        if regime:
            regime_clusters = [
                _render_broadcast_cluster(
                    handle=handle,
                    items=items,
                    kind="regime",
                    tier=4,
                    source_for_filter="Regime channels",
                )
                for handle, items in sorted(regime.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            ]
            sub_blocks.append(
                '<div class="broadcast-sub broadcast-sub-regime">'
                '<h5 class="broadcast-sub-caption">Regime channels · claims, not facts</h5>'
                + "".join(regime_clusters)
                + '</div>'
            )

        parts.append(
            '<div class="broadcast-zone" aria-label="Broadcast layer">'
            '<h4 class="broadcast-zone-caption">Broadcast layer · expand to read individual posts</h4>'
            + "".join(sub_blocks)
            + '</div>'
        )

    return "\n".join(parts)


def _render_broadcast_cluster(
    *,
    handle: str,
    items: list[dict],
    kind: str,                 # "military" or "regime"
    tier: int,
    source_for_filter: str,
) -> str:
    """One collapsible block per broadcast handle — header is the teaser,
    body is the individual events hidden by default. Used for both military
    spokes (IDF, CENTCOM at tier 2) and regime channels (Telegram at
    tier 4). The `kind` attribute drives the visual treatment in CSS."""
    # Newest first within the cluster.
    items_sorted = sorted(items, key=lambda e: e.get("published_at") or "", reverse=True)
    n = len(items_sorted)
    latest = items_sorted[0]
    oldest = items_sorted[-1]

    details = latest.get("details") or {}
    display = details.get("channel_display") or details.get("handle") or handle
    detail = latest.get("source_detail") or ""
    teaser_title = latest.get("title_en") or latest.get("title") or ""
    latest_at = (latest.get("published_at") or "")[:16].replace("T", " ")
    oldest_at = (oldest.get("published_at") or "")[:16].replace("T", " ")
    range_label = (
        f"{oldest_at}Z → {latest_at}Z" if n > 1 else f"{latest_at}Z"
    )

    # Dedup: skip the teased latest item in the expander when there's more
    # than one post in the cluster — the teaser snippet at the top of the
    # cluster header is already showing it. For single-post clusters the
    # expander reveals the one post in full (the snippet is a preview).
    expander_items = items_sorted[1:] if n > 1 else items_sorted
    children = "\n".join(_render_event(e) for e in expander_items)

    n_figures = sum(1 for e in items_sorted if e.get("has_figures"))
    has_figures_any = n_figures > 0
    fig_count_html = (
        f'<span class="cluster-figures" title="Posts in this cluster citing specific figures">'
        f'{n_figures} with fig.</span>'
        if has_figures_any else ""
    )

    # data-child-ids carries every child the cluster represents (including
    # the teased latest), so thread-filters can match the cluster on any
    # of its posts.
    child_ids = "|".join(e.get("id") or "" for e in items_sorted)
    if n > 1:
        prev_n = n - 1
        expand_label = f"Expand to read previous {prev_n} post{'s' if prev_n != 1 else ''}"
    else:
        expand_label = "Expand to read full post"

    # Truncate the teaser hard. The full text of the latest post lives in
    # the expander; this is a body-register preview snippet, not a headline.
    # Iran International / Bluesky / Telegram items in the document zone
    # still get their Playfair headlines — the editorial hierarchy is
    # documents at headline-weight, broadcasts at snippet-weight.
    teaser_snippet = _truncate_teaser(teaser_title, max_chars=120)

    return (
        f'<article class="event channel-cluster" '
        f'data-source="{html.escape(source_for_filter)}" data-tier="{tier}" '
        f'data-figures="{1 if has_figures_any else 0}" '
        f'data-channel="{html.escape(handle)}" '
        f'data-cluster-kind="{kind}" '
        f'data-child-ids="{html.escape(child_ids)}">'
        '<button class="cluster-toggle" type="button" aria-expanded="false">'
        '<div class="head">'
        '<div class="source-info">'
        '<div class="src-row">'
        f'<span class="tier-mark t{tier}" aria-hidden="true"></span>'
        f'<span class="src">{html.escape(display)}</span>'
        f'<span class="cluster-count">{n} post{"s" if n != 1 else ""}</span>'
        f'{fig_count_html}'
        f'{_translated_badge_html(latest)}'
        '</div>'
        f'<div class="src-detail">{html.escape(detail)}</div>'
        '</div>'
        f'<div class="time">{html.escape(range_label)}</div>'
        '</div>'
        f'<p class="cluster-teaser">'
        f'<span class="cluster-teaser-label">Latest:</span> '
        f'<span class="cluster-teaser-snippet">“{html.escape(html.unescape(teaser_snippet))}”</span>'
        '</p>'
        f'<div class="cluster-foot">'
        f'<span class="cluster-expand">{expand_label}</span>'
        '</div>'
        '</button>'
        f'<div class="cluster-body" hidden>{children}</div>'
        '</article>'
    )


def _truncate_teaser(text: str, max_chars: int = 120) -> str:
    """Trim a teaser snippet to max_chars, breaking at a word boundary,
    appending an ellipsis when truncated. Preserves leading whitespace from
    the source where present (some Telegram posts open with emoji)."""
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:—–-") + "…"


def _render_day_shape(day_shape: str, n_items: int) -> str:
    """The one-sentence shape-of-the-day line. Sits above the threads block.

    The model writes a single concrete sentence describing the most
    consequential developments and noteworthy absences. This is the 5-second
    skim a 7am editor reads before scrolling. We render it with a small
    sans-caps marker ("TODAY'S SHAPE") and the headline-weight text on its
    own row so it carries genuine editorial weight without competing with
    the threads block beneath.
    """
    if not day_shape:
        return ""
    text = html.escape(html.unescape(day_shape))
    return (
        '<section class="day-shape" aria-label="Day shape">'
        '<span class="day-shape-label">Today’s shape</span>'
        f'<p class="day-shape-text">{text}</p>'
        '</section>'
    )


def _render_threads(threads: list[dict]) -> str:
    if not threads:
        return ""
    items = []
    for i, t in enumerate(threads, 1):
        label = html.escape(html.unescape(t.get("label") or ""))
        summary = html.escape(html.unescape(t.get("summary") or ""))
        event_ids = t.get("event_ids") or []
        n = len(event_ids)
        tier4 = t.get("tier4_present")
        tier4_badge = (
            ' <span class="thread-tier4" title="Includes regime-channel claims">includes claims</span>'
            if tier4 else ""
        )
        ids_attr = html.escape("|".join(event_ids))
        items.append(
            '<li class="thread">'
            f'<button class="thread-btn" type="button" '
            f'data-thread-ids="{ids_attr}" data-active="0" '
            'aria-pressed="false" '
            'title="Click to filter the events below to just this thread\'s items. Click again to clear.">'
            f'<div class="thread-num">{i:02d}</div>'
            '<div class="thread-body">'
            f'<h3 class="thread-label">{label}{tier4_badge}</h3>'
            f'<p class="thread-summary">{summary}</p>'
            '<div class="thread-foot">'
            f'<span class="thread-count">{n} item{"s" if n != 1 else ""}</span>'
            '<span class="thread-action">→ filter events</span>'
            '</div>'
            '</div>'
            '</button>'
            '</li>'
        )
    threads_word = "Seven" if len(threads) == 7 else ("Six" if len(threads) == 6 else "Five")
    return (
        '<section class="threads" aria-label="Threads">'
        f'<div class="threads-head"><h4>{threads_word} threads today</h4>'
        '<span class="threads-disclaimer">Auto-clustered by Claude. No analysis — just what was reported. Click a thread to filter the events below.</span>'
        '</div>'
        f'<ol>{"".join(items)}</ol>'
        '</section>'
    )


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
        "href": "compare-isw-2026-05-01.html",
        "title": "1 May 2026 · sharpest case yet",
        "blurb": (
            "37 matched items. We landed both of the day's State Department "
            "oil-trade sanctions designations on the same day, and have the "
            "full Khamenei Workers' Day / Persian Gulf messaging cycle direct "
            "from regime channels — which ISW only references obliquely. "
            "Both outputs lead with the economic-collapse story from "
            "different sourcing paths."
        ),
    },
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


def render_home(latest_stem: str | None) -> str:
    """The homepage: most recent brief shown inline, framed as 'Today's report'."""
    if latest_stem:
        payload = json.loads((DATA_DIR / f"{latest_stem}.json").read_text())
        events = payload.get("events", [])
        try:
            pretty_date = datetime.fromisoformat(latest_stem).strftime("%A %d %B %Y")
        except ValueError:
            pretty_date = latest_stem
        generated_at = payload.get("generated_at") or ""

        intro = (
            f'<header class="page-header">'
            f'<h1>Today’s report</h1>'
            f'<div class="meta">'
            f'{html.escape(pretty_date)}'
            f' <span class="dot">·</span> {len(events)} items'
            f' <span class="dot">·</span> last updated '
            f'<time class="last-updated" datetime="{html.escape(generated_at)}" '
            f'data-generated-at="{html.escape(generated_at)}">{html.escape(generated_at[:16].replace("T", " "))}Z</time>'
            f'</div>'
            f'</header>'
        )
        brief = _brief_body(payload, include_diagnostics=False)
    else:
        intro = (
            '<header class="page-header">'
            '<h1>Today’s report</h1>'
            '<div class="meta">No briefs yet — the daily cron will fill these in.</div>'
            '</header>'
        )
        brief = ""

    body = intro + brief
    return _page("Iran Watcher", body, current_nav="home")


def render_archive(dated_days: list[tuple[str, int]]) -> str:
    """The full chronological archive of dated daily briefs."""
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

    body = (
        '<header class="page-header">'
        '<h1>Archive</h1>'
        f'<div class="meta">{len(archive_rows)} daily briefs.</div>'
        '</header>'

        '<section class="archive" aria-label="Daily archive">'
        + ("".join(archive_rows) if archive_rows
           else '<p class="empty">No daily briefs yet.</p>')
        + '</section>'
    )
    return _page("Archive — Iran Watcher", body, current_nav="archive")


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
    return _page("Comparisons — Iran Watcher", body, current_nav="comparisons")


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
    (DOCS_DIR / "index.html").write_text(render_home(latest_dated))
    print(f"  wrote index.html (latest={latest_dated})", file=sys.stderr)

    (DOCS_DIR / "archive.html").write_text(render_archive(days_for_archive))
    print(f"  wrote archive.html ({len(days_for_archive)} entries)", file=sys.stderr)

    (DOCS_DIR / "comparisons.html").write_text(render_comparisons())
    print(f"  wrote comparisons.html", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
