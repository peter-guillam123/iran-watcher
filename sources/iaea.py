"""IAEA — International Atomic Energy Agency news feed.

The 'Top Stories' feed at /feeds/news returns ~150 recent items covering
the IAEA's worldwide activity. Iran-relevant filtering is handled in
collect.py; this adapter just normalises the feed.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser
import httpx

FEED = "https://www.iaea.org/feeds/news"
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
        title = (e.get("title") or "").strip()
        link = e.get("link") or ""
        out.append({
            "id": f"iaea:{e.get('id') or link}",
            "source": "IAEA",
            "source_tier": 2,
            "published_at": pub.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": link,
            "summary": _strip_html(e.get("summary") or e.get("description") or "")[:500],
            "tags": ["nuclear"],
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
