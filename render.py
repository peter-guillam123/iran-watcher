"""Render today's data/YYYY-MM-DD.json to docs/YYYY-MM-DD.html and update docs/index.html.

Filter pills along the top let the reader narrow by source family. Parliament
items get a richer layout that exposes the asking/answering members and the
full Q&A text rather than a truncated summary."""

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

PAGE_CSS = """\
*{box-sizing:border-box}
body{font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;margin:0;color:#1a1a1a;background:#fafafa}
main{max-width:780px;margin:0 auto;padding:32px 20px 80px}
header{margin-bottom:24px}
header h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
header .meta{color:#666;font-size:14px}
nav.top{margin:12px 0 0;font-size:14px}
nav.top a{color:#0a4f8f;text-decoration:none;margin-right:16px}
nav.top a:hover{text-decoration:underline}

.filters{margin:24px 0 16px;padding:14px 14px 8px;background:#fff;border:1px solid #e2e2e2;border-radius:8px}
.filter-row{margin-bottom:8px}
.filter-row:last-child{margin-bottom:0}
.sort-row{padding-top:8px;border-top:1px solid #f0f0f0}
.filters h4{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#888;margin:0 0 8px;font-weight:600}
.pill,.sort-pill{display:inline-flex;align-items:baseline;gap:6px;padding:5px 12px;margin:0 6px 6px 0;border:1px solid #d0d0d0;border-radius:18px;background:#fff;color:#333;font-size:14px;cursor:pointer;user-select:none;transition:background .12s,color .12s,border-color .12s;font-family:inherit}
.pill:hover,.sort-pill:hover{border-color:#888}
.pill .n,.sort-pill .n{font-variant-numeric:tabular-nums;color:#666;font-size:12px}
.pill[data-active="1"],.sort-pill[data-active="1"]{background:#1a1a1a;color:#fff;border-color:#1a1a1a}
.pill[data-active="1"] .n,.sort-pill[data-active="1"] .n{color:#bbb}
.pill.all{background:#f0f0f0}
.pill.all[data-active="1"]{background:#1a1a1a;color:#fff}

.tier-header{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:600;margin:28px 0 4px;padding-bottom:4px;border-bottom:1px solid #eee}
.tier-header:first-child{margin-top:8px}
.tier-header.hidden{display:none}
.tier-header.t1{color:#2a672a}
.tier-header.t2{color:#3a55a8}
.tier-header.t3{color:#8a4a17}

.day-nav{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:14px 0 4px;padding:10px 14px;background:#fff;border:1px solid #e2e2e2;border-radius:8px;font-size:14px}
.day-nav.bottom{margin-top:32px}
.day-nav a{color:#0a4f8f;text-decoration:none;flex:1}
.day-nav a:hover{text-decoration:underline}
.day-nav a.next{text-align:right}
.day-nav a.hub{flex:0;color:#666;font-size:13px;text-align:center;padding:0 12px}
.day-nav .disabled{color:#ccc;flex:1}
.day-nav .next.disabled{text-align:right}

.event{padding:18px 0;border-top:1px solid #e2e2e2}
.event:first-of-type{border-top:none}
.event .head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:6px}
.event .source-line{font-size:13px;color:#555;flex:1;min-width:0}
.event .source-line .src{font-weight:600;color:#1a1a1a}
.event .time{color:#888;font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.event h3{margin:0 0 6px;font-size:18px;line-height:1.35}
.event h3 a{color:#1a1a1a;text-decoration:none}
.event h3 a:hover{color:#0a4f8f;text-decoration:underline}
.event .summary{color:#333;margin:6px 0 0;font-size:15px}
.event .tags{margin-top:8px}
.tag{display:inline-block;padding:1px 8px;font-size:11px;background:#eef;color:#3a55a8;border-radius:10px;margin-right:6px;letter-spacing:.02em;text-transform:lowercase}
.tag.tier{background:#f0f0f0;color:#555}
.tag.tier-1{background:#e6f3e6;color:#2a672a}
.tag.tier-2{background:#eef;color:#3a55a8}
.tag.tier-3{background:#fbeede;color:#8a4a17}

/* Parliament rich layout */
.parl{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:14px 16px;margin-top:6px}
.parl .meta{font-size:13px;color:#555;margin-bottom:8px}
.parl .meta .actor{color:#1a1a1a;font-weight:600}
.parl .meta .arrow{color:#bbb;margin:0 6px}
.parl .qa{font-size:15px;line-height:1.5}
.parl .qa-block{margin:8px 0}
.parl .qa-label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#888;margin-bottom:4px;font-weight:600}
.parl .qa-text{color:#222}
.parl .answer-meta{font-size:12px;color:#777;margin-top:2px;font-style:italic}

.diag{margin-top:48px;padding:14px 16px;background:#f4f4f4;border-radius:6px;font-size:13px;color:#555}
.diag h4{margin:0 0 6px;font-size:13px;color:#333}
.diag code{font-family:ui-monospace,Menlo,Monaco,monospace;font-size:12px}
footer{margin-top:48px;padding-top:24px;border-top:1px solid #e2e2e2;color:#888;font-size:13px}
footer a{color:#666}
.empty{padding:32px 0;text-align:center;color:#666;font-style:italic}
.hidden{display:none}
.party{font-size:11px;padding:1px 6px;border-radius:8px;margin-left:4px;color:#fff;background:#777;font-weight:500;letter-spacing:.02em;text-transform:none}
.party.lab{background:#d40000}
.party.con{background:#0087dc}
.party.ld{background:#faa61a;color:#000}
.party.snp{background:#fff95d;color:#000}
.party.xb{background:#888}
.party.gov{background:#00558e}
"""

INDEX_CSS = """\
*{box-sizing:border-box}
body{font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;margin:0;color:#1a1a1a;background:#fafafa}
main{max-width:680px;margin:0 auto;padding:32px 20px 80px}
header h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
header .meta{color:#666;font-size:14px}
nav.top{margin:12px 0 24px;font-size:14px}
nav.top a{color:#0a4f8f;text-decoration:none;margin-right:16px}
.day{padding:14px 0;border-top:1px solid #e2e2e2;display:flex;justify-content:space-between;align-items:baseline}
.day:first-of-type{border-top:none}
.day a{font-size:18px;color:#0a4f8f;text-decoration:none}
.day a:hover{text-decoration:underline}
.day .count{color:#666;font-size:14px;font-variant-numeric:tabular-nums}
.empty{padding:32px 0;text-align:center;color:#666;font-style:italic}
"""

FILTER_JS = r"""
(function(){
  var pills = document.querySelectorAll('.pill[data-source]');
  var allPill = document.querySelector('.pill.all');
  var eventsBox = document.querySelector('.events');
  var sortDate = document.querySelector('.sort-pill[data-sort="date"]');
  var sortTier = document.querySelector('.sort-pill[data-sort="tier"]');
  var originalHTML = eventsBox ? eventsBox.innerHTML : '';

  function activeSources(){
    var s = new Set();
    pills.forEach(function(p){ if(p.dataset.active === '1') s.add(p.dataset.source); });
    return s;
  }

  function applyFilter(){
    if(!eventsBox) return;
    var s = activeSources();
    var events = eventsBox.querySelectorAll('.event');
    var headers = eventsBox.querySelectorAll('.tier-header');
    if(s.size === 0){
      events.forEach(function(e){ e.classList.remove('hidden'); });
      headers.forEach(function(h){ h.classList.remove('hidden'); });
      allPill.dataset.active = '1';
    } else {
      allPill.dataset.active = '0';
      events.forEach(function(e){ e.classList.toggle('hidden', !s.has(e.dataset.source)); });
      // Hide tier headers whose group has no visible events.
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


def _party_class(party: str | None) -> str:
    if not party:
        return ""
    p = party.lower()
    if "labour" in p:
        return "lab"
    if "conservative" in p:
        return "con"
    if "liberal democrat" in p:
        return "ld"
    if "scottish national" in p or "snp" in p:
        return "snp"
    if "crossbench" in p:
        return "xb"
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
        return f'<div class="parl">{meta}<div class="qa">{body}</div></div>'

    # Question or answer
    asker_pill = _party_pill(asking) if asking else "<span class=\"actor\">(unknown)</span>"
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
    return f'<div class="parl">{meta}<div class="qa">{body}</div></div>'


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
        f'<div class="source-line"><span class="src">{source_h}</span>'
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
    tier_pill = f'<span class="tag tier tier-{tier}">tier {tier}</span>'

    return (
        f'<article class="event" data-source="{html.escape(source)}" '
        f'data-category="{html.escape(cat)}" data-tier="{tier}">'
        f'{head}{body}'
        f'<div class="tags">{tier_pill}{tag_html}</div>'
        f'</article>'
    )


def _render_pills(events: list[dict]) -> str:
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
        '<section class="filters">'
        '<div class="filter-row"><h4>Filter by source</h4>'
        + "".join(filter_pills)
        + '</div>'
        '<div class="filter-row sort-row"><h4>Sort by</h4>'
        + sort_pills
        + '</div>'
        "</section>"
    )


def render_day(
    date_str: str,
    prev_stem: str | None = None,
    next_stem: str | None = None,
) -> str:
    payload = json.loads((DATA_DIR / f"{date_str}.json").read_text())
    events = payload.get("events", [])
    diagnostics = payload.get("diagnostics", [])

    try:
        pretty_date = datetime.fromisoformat(date_str).strftime("%A %d %B %Y")
    except ValueError:
        pretty_date = date_str.replace("-", " ").title()

    pills_html = _render_pills(events) if events else ""
    items_html = "\n".join(_render_event(e) for e in events)
    if not items_html:
        items_html = '<p class="empty">No items matched the Iran/Middle East filter in this window.</p>'

    diag_rows = []
    for d in diagnostics:
        if d.get("ok"):
            diag_rows.append(
                f'<li><code>{html.escape(d["source"])}</code> — fetched {d["fetched"]}, kept {d["kept"]}</li>'
            )
        else:
            diag_rows.append(
                f'<li><code>{html.escape(d["source"])}</code> — '
                f'error: {html.escape((d.get("error") or "")[:200])}</li>'
            )
    diag_html = "<ul>" + "".join(diag_rows) + "</ul>" if diag_rows else ""

    window_since = (payload.get("window_since") or "")[:16].replace("T", " ")
    window_until = (payload.get("window_until") or "")[:16].replace("T", " ")

    def _pretty(stem: str) -> str:
        try:
            return datetime.fromisoformat(stem).strftime("%a %d %b")
        except ValueError:
            return stem
    prev_link = (
        f'<a class="prev" href="{prev_stem}.html">← {_pretty(prev_stem)}</a>'
        if prev_stem else '<span class="prev disabled">← earlier</span>'
    )
    next_link = (
        f'<a class="next" href="{next_stem}.html">{_pretty(next_stem)} →</a>'
        if next_stem else '<span class="next disabled">later →</span>'
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Iran watcher — {pretty_date}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{PAGE_CSS}</style>
</head><body><main>
<header>
  <h1>Iran watcher · {pretty_date}</h1>
  <div class="meta">{len(events)} items · window {window_since}Z to {window_until}Z</div>
  <nav class="top"><a href="./">All days</a> <a href="about.html">About</a> <a href="changelog.html">Changelog</a></nav>
</header>
<nav class="day-nav">{prev_link}<a class="hub" href="./">All days</a>{next_link}</nav>
{pills_html}
<section class="events">{items_html}</section>
<nav class="day-nav bottom">{prev_link}<a class="hub" href="./">All days</a>{next_link}</nav>
<section class="diag">
  <h4>Source run</h4>
  {diag_html}
</section>
<footer>
  Generated {payload.get("generated_at", "")[:19].replace("T", " ")}Z. See <a href="about.html">About</a> for what's in and what isn't.
</footer>
<script>{FILTER_JS}</script>
</main></body></html>
"""


FEATURED_INDEX_BLOCK = """\
<section class="featured">
  <h3>Featured</h3>
  <a class="feat" href="compare-isw.html">
    <div class="feat-title">Comparison vs. ISW Iran Update — 30 April 2026</div>
    <div class="feat-blurb">A like-for-like read of our matched-window output against the ISW report covering the same calendar window.</div>
  </a>
  <a class="feat" href="last-7-days-demo.html">
    <div class="feat-title">7-day demo (54 items, all sources)</div>
    <div class="feat-blurb">A wider window so the filter pills and the Parliament rich layout have something to demonstrate against. Goes away once the daily cron has accumulated a few days.</div>
  </a>
</section>
"""

INDEX_FEATURED_CSS = """\
.featured{margin:24px 0 32px;padding:14px 16px;background:#fff;border:1px solid #e2e2e2;border-radius:8px}
.featured h3{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#888;margin:0 0 10px;font-weight:600}
.feat{display:block;padding:12px;margin:0 0 8px;border-radius:6px;background:#f7f7f7;text-decoration:none;color:inherit}
.feat:hover{background:#eef5ff}
.feat:last-child{margin-bottom:0}
.feat-title{font-weight:600;color:#0a4f8f;margin-bottom:2px}
.feat-blurb{font-size:13px;color:#555}
"""


def render_index(days: list[tuple[str, int]]) -> str:
    # Only show ISO-date stems in the daily list. Non-date labels (demos,
    # comparisons) get hand-rolled cards in the Featured section instead.
    rows = []
    for date_str, count in days:
        try:
            pretty = datetime.fromisoformat(date_str).strftime("%a %d %b %Y")
        except ValueError:
            continue
        rows.append(
            f'<div class="day"><a href="{date_str}.html">{pretty}</a>'
            f'<span class="count">{count} items</span></div>'
        )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Iran watcher</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{INDEX_CSS}{INDEX_FEATURED_CSS}</style>
</head><body><main>
<header>
  <h1>Iran watcher</h1>
  <div class="meta">A daily-updated tip-sheet of primary governmental and multilateral sources on Iran and the Middle East crisis.</div>
  <nav class="top"><a href="about.html">About</a> <a href="changelog.html">Changelog</a></nav>
</header>
{FEATURED_INDEX_BLOCK}
<h3 style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#888;margin:24px 0 8px;font-weight:600">Daily briefs</h3>
{''.join(rows) if rows else '<p class="empty">No daily briefs yet — the cron will fill these in.</p>'}
</main></body></html>
"""


def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # Build the list of all dated stems (sorted ascending) so we can compute
    # prev/next nav. Non-date stems (demos, comparisons) are excluded from
    # prev/next chaining but still rendered.
    all_stems = [p.stem for p in sorted(DATA_DIR.glob("*.json"))]
    dated = []
    for stem in all_stems:
        try:
            datetime.fromisoformat(stem)
            dated.append(stem)
        except ValueError:
            continue
    # Map each stem to its older/newer neighbour by date (ascending list).
    prev_of: dict[str, str | None] = {}
    next_of: dict[str, str | None] = {}
    for i, stem in enumerate(dated):
        prev_of[stem] = dated[i - 1] if i > 0 else None
        next_of[stem] = dated[i + 1] if i + 1 < len(dated) else None

    days: list[tuple[str, int]] = []
    # Render newest-first for nicer console output.
    for stem in reversed(all_stems):
        payload = json.loads((DATA_DIR / f"{stem}.json").read_text())
        count = len(payload.get("events", []))
        out = DOCS_DIR / f"{stem}.html"
        out.write_text(render_day(stem, prev_of.get(stem), next_of.get(stem)))
        days.append((stem, count))
        print(f"  wrote {out.name} ({count} items)", file=sys.stderr)

    (DOCS_DIR / "index.html").write_text(render_index(days))
    print(f"  wrote index.html ({len(days)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
