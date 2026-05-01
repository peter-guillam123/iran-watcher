"""Render today's data/YYYY-MM-DD.json to docs/YYYY-MM-DD.html and update docs/index.html."""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

PAGE_CSS = """\
*{box-sizing:border-box}
body{font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;margin:0;color:#1a1a1a;background:#fafafa}
main{max-width:760px;margin:0 auto;padding:32px 20px 80px}
header{margin-bottom:32px}
header h1{font-size:28px;margin:0 0 4px;letter-spacing:-.01em}
header .meta{color:#666;font-size:14px}
nav{margin:16px 0 0;font-size:14px}
nav a{color:#0a4f8f;text-decoration:none;margin-right:16px}
nav a:hover{text-decoration:underline}
.event{padding:16px 0;border-top:1px solid #e2e2e2}
.event:first-of-type{border-top:none}
.event h3{margin:0 0 4px;font-size:18px;line-height:1.35}
.event h3 a{color:#1a1a1a;text-decoration:none}
.event h3 a:hover{color:#0a4f8f;text-decoration:underline}
.event .source{font-size:13px;color:#555;margin-bottom:6px}
.event .source .time{color:#888;margin-left:8px}
.event .summary{color:#333;margin:6px 0 0;font-size:15px}
.event .tags{margin-top:6px}
.tag{display:inline-block;padding:1px 8px;font-size:11px;background:#eef;color:#3a55a8;border-radius:10px;margin-right:6px;letter-spacing:.02em;text-transform:lowercase}
.tag.tier-1{background:#e6f3e6;color:#2a672a}
.tag.tier-2{background:#eef;color:#3a55a8}
.tag.tier-3{background:#fbeede;color:#8a4a17}
.diag{margin-top:48px;padding:14px 16px;background:#f4f4f4;border-radius:6px;font-size:13px;color:#555}
.diag h4{margin:0 0 6px;font-size:13px;color:#333}
.diag code{font-family:ui-monospace,Menlo,Monaco,monospace;font-size:12px}
footer{margin-top:48px;padding-top:24px;border-top:1px solid #e2e2e2;color:#888;font-size:13px}
footer a{color:#666}
.empty{padding:32px 0;text-align:center;color:#666;font-style:italic}
"""

INDEX_CSS = PAGE_CSS + """\
.day{padding:14px 0;border-top:1px solid #e2e2e2;display:flex;justify-content:space-between;align-items:baseline}
.day:first-of-type{border-top:none}
.day a{font-size:18px;color:#0a4f8f;text-decoration:none}
.day a:hover{text-decoration:underline}
.day .count{color:#666;font-size:14px}
"""


def render_day(date_str: str) -> str:
    payload = json.loads((DATA_DIR / f"{date_str}.json").read_text())
    events = payload.get("events", [])
    diagnostics = payload.get("diagnostics", [])

    items_html = []
    for e in events:
        title = html.escape(html.unescape(e.get("title") or "(untitled)"))
        url = html.escape(e.get("url") or "#")
        source = html.escape(e.get("source") or "")
        tier = e.get("source_tier") or 2
        published = (e.get("published_at") or "")[:16].replace("T", " ")
        # Some RSS sources (State Dept) ship summaries with HTML entities
        # already encoded; unescape first so we don't double-escape.
        summary = html.escape(html.unescape(e.get("summary") or ""))
        tags = e.get("tags") or []
        tags_html = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)

        items_html.append(f"""
<article class="event">
  <h3><a href="{url}" rel="noopener">{title}</a></h3>
  <div class="source">{source} <span class="time">· {published}Z</span></div>
  {f'<p class="summary">{summary}</p>' if summary else ''}
  <div class="tags"><span class="tag tier-{tier}">tier {tier}</span>{tags_html}</div>
</article>""".strip())

    body = "\n".join(items_html) if items_html else '<p class="empty">No items matched the Iran/Middle East filter today.</p>'

    diag_rows = []
    for d in diagnostics:
        if d.get("ok"):
            diag_rows.append(f'<li><code>{html.escape(d["source"])}</code> — fetched {d["fetched"]}, kept {d["kept"]}</li>')
        else:
            diag_rows.append(f'<li><code>{html.escape(d["source"])}</code> — error: {html.escape((d.get("error") or "")[:200])}</li>')
    diag_html = "<ul>" + "".join(diag_rows) + "</ul>" if diag_rows else ""

    pretty_date = datetime.fromisoformat(date_str).strftime("%A %d %B %Y")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Iran watcher — {pretty_date}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{PAGE_CSS}</style>
</head><body><main>
<header>
  <h1>Iran watcher · {pretty_date}</h1>
  <div class="meta">{len(events)} items from primary government and multilateral sources</div>
  <nav><a href="./">All days</a> <a href="about.html">About</a> <a href="changelog.html">Changelog</a></nav>
</header>
{body}
<section class="diag">
  <h4>Source run</h4>
  {diag_html}
</section>
<footer>
  Generated {payload.get("generated_at", "")[:19].replace("T", " ")}Z. Sources: tier 1 = clean APIs, tier 2 = RSS, tier 3 = scraped HTML. See <a href="about.html">About</a>.
</footer>
</main></body></html>
"""


def render_index(days: list[tuple[str, int]]) -> str:
    rows = []
    for date_str, count in days:
        try:
            pretty = datetime.fromisoformat(date_str).strftime("%a %d %b %Y")
        except ValueError:
            pretty = date_str
        rows.append(f'<div class="day"><a href="{date_str}.html">{pretty}</a><span class="count">{count} items</span></div>')

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Iran watcher</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{INDEX_CSS}</style>
</head><body><main>
<header>
  <h1>Iran watcher</h1>
  <div class="meta">A daily-updated tip-sheet of primary governmental and multilateral sources on Iran and the Middle East crisis.</div>
  <nav><a href="about.html">About</a> <a href="changelog.html">Changelog</a></nav>
</header>
{''.join(rows) if rows else '<p class="empty">No data yet.</p>'}
</main></body></html>
"""


def main() -> int:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    days: list[tuple[str, int]] = []
    for path in sorted(DATA_DIR.glob("*.json"), reverse=True):
        date_str = path.stem
        payload = json.loads(path.read_text())
        count = len(payload.get("events", []))
        out = DOCS_DIR / f"{date_str}.html"
        out.write_text(render_day(date_str))
        days.append((date_str, count))
        print(f"  wrote {out.name} ({count} items)", file=sys.stderr)

    (DOCS_DIR / "index.html").write_text(render_index(days))
    print(f"  wrote index.html ({len(days)} days)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
