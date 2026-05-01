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
        title = (e.get("title") or "").strip()
        raw_summary = _strip_html(e.get("summary") or e.get("description") or "")
        summary = _clean_state_summary(raw_summary, title)[:500]
        out.append({
            "id": ev_id,
            "source": "US State Department",
            "source_detail": label,
            "source_tier": 2,
            "category": "state-press",
            "published_at": pub.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": link,
            "summary": summary,
            "details": {},
            "tags": ["diplomatic"],
        })
    return out


# State Dept RSS bodies start with the same boilerplate as the headline:
#   "Tommy Pigott, Department Spokesperson  <Title>  Press Statement <Date>  <real text>"
# We want only the <real text>. Strip the prefix.
def _clean_state_summary(s: str, title: str) -> str:
    import re
    # Drop common spokesperson-byline prefixes.
    s = re.sub(r"^\s*(Office of the Spokesperson|Thomas\s+\S+\s+Pigott,\s+Department Spokesperson|[A-Z][a-zA-Z\s\.]+,\s+(?:Department Spokesperson|Spokesperson))\s*", "", s)
    # If the headline is repeated verbatim in the body, drop that copy.
    if title and title in s:
        s = s.replace(title, "", 1).strip()
    # Drop "Press Statement DATE" or "Readout DATE" lead-ins.
    s = re.sub(r"^\s*(Press Statement|Readout|Statement|Media Note)\s+(?:[A-Z][a-z]+\s+\d{1,2},\s+\d{4}\s*)?", "", s)
    return s.strip(" :;-—\n\t")


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
