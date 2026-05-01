"""UN Meetings Coverage and Press Releases — RSS feed.

The feed is global (10 most recent items across all topics). The keyword
filter in collect.py drops anything that isn't Iran/Middle-East-relevant.

Limitation: at peak UN activity 10 items can roll over within hours,
which means we could miss Iran items if collect runs less often than
that. The collector runs twice a day, which is fine in practice but
worth flagging on the About page.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser
import httpx

FEED = "https://press.un.org/en/rss.xml"


def fetch(since: datetime) -> list[dict]:
    r = httpx.get(FEED, follow_redirects=True, timeout=30)
    r.raise_for_status()
    d = feedparser.parse(r.text)

    out = []
    for e in d.entries:
        pub = _parse_date(e.get("published") or e.get("updated") or "")
        if pub is None or pub < since:
            continue
        title = (e.get("title") or "").strip()
        link = e.get("link") or ""
        body, category = _classify(title, link)
        out.append({
            "id": f"unpress:{e.get('id') or link}",
            "source": "UN Press",
            "source_detail": body,
            "source_tier": 2,
            "category": category,
            "published_at": pub.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": link,
            "summary": _strip_html(e.get("summary") or e.get("description") or "")[:500],
            "details": {},
            "tags": _tags(title),
        })
    return out


def _classify(title: str, link: str) -> tuple[str, str]:
    t = title.lower()
    if "security council" in t or "/sc" in link.lower():
        return "Security Council", "un-security-council"
    if "general assembly" in t or "/ga" in link.lower():
        return "General Assembly", "un-general-assembly"
    if "secretary-general" in t or "/sgsm" in link.lower():
        return "Secretary-General", "un-secretary-general"
    return "Press release", "un-press"


def _tags(title: str) -> list[str]:
    t = title.lower()
    tags = []
    if "nuclear" in t or "iaea" in t:
        tags.append("nuclear")
    if "sanction" in t:
        tags.append("sanctions")
    if "ceasefire" in t or "strike" in t or "missile" in t:
        tags.append("military")
    return tags or ["diplomatic"]


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
