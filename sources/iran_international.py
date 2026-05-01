"""Iran International — London-based Persian-language opposition outlet.

Used as a triangulation layer for what's happening inside Iran while
direct access to IRNA/Tasnim/IRIB is impractical (50+ day Iran internet
blackout, 'Absolute Digital Isolation' policy). Marked tier 3 because
it isn't a primary government source — it's media — and the editorial
slant should be visible to anyone reading the brief.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser
import httpx

FEED = "https://www.iranintl.com/en/feed"
USER_AGENT = "Mozilla/5.0 iran-watcher (chris.moran@guardian.co.uk)"


def fetch(since: datetime) -> list[dict]:
    r = httpx.get(FEED, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
    r.raise_for_status()
    d = feedparser.parse(r.text)

    out = []
    for e in d.entries:
        pub = _parse_date(e.get("published") or e.get("updated") or "")
        if pub is None or pub < since:
            continue
        link = e.get("link") or ""
        out.append({
            "id": f"iranintl:{e.get('id') or link}",
            "source": "Iran International (opposition outlet, London)",
            "source_tier": 3,
            "published_at": pub.isoformat().replace("+00:00", "Z"),
            "title": (e.get("title") or "").strip(),
            "url": link,
            "summary": _strip_html(e.get("summary") or "")[:500],
            "tags": ["iran-domestic"],
        })
    return out


def _parse_date(s: str):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
