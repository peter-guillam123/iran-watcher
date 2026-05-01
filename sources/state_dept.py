"""US Department of State — official RSS feeds.

Pulls from three feeds and dedupes:
  - press-releases (highest volume, all topics)
  - near-east (regional feed — covers Iran, Israel, Gulf states)
  - secretarys-remarks (Secretary's interviews and statements)

Iran filtering is handled by collect.py.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser
import httpx

FEEDS = [
    ("press-releases", "https://www.state.gov/rss-feed/press-releases/feed/"),
    ("near-east",      "https://www.state.gov/rss-feed/near-east/feed/"),
    ("secretarys-remarks", "https://www.state.gov/rss-feed/secretarys-remarks/feed/"),
]
USER_AGENT = "Mozilla/5.0 iran-watcher (chris.moran@guardian.co.uk)"


def fetch(since: datetime) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for label, url in FEEDS:
        out.extend(_fetch_one(label, url, since, seen))
    return out


def _fetch_one(label: str, url: str, since: datetime, seen: set[str]) -> list[dict]:
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
    r.raise_for_status()
    d = feedparser.parse(r.text)

    out = []
    for e in d.entries:
        pub = _parse_date(e.get("published") or e.get("updated") or "")
        if pub is None or pub < since:
            continue
        link = e.get("link") or ""
        ev_id = f"state:{e.get('id') or link}"
        if ev_id in seen:
            continue
        seen.add(ev_id)
        out.append({
            "id": ev_id,
            "source": f"US State Department ({label})",
            "source_tier": 2,
            "published_at": pub.isoformat().replace("+00:00", "Z"),
            "title": (e.get("title") or "").strip(),
            "url": link,
            "summary": _strip_html(e.get("summary") or e.get("description") or "")[:500],
            "tags": ["diplomatic"],
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
