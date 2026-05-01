"""GOV.UK Atom feeds for key UK government departments.

Every department on gov.uk exposes a stable Atom feed at
.../organisations/<slug>.atom. We pull from the five most relevant for
this beat. Iran filtering happens in collect.py — these feeds are
department-wide.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
import feedparser
import httpx

DEPARTMENTS = [
    ("Foreign, Commonwealth and Development Office",
     "https://www.gov.uk/government/organisations/foreign-commonwealth-development-office.atom"),
    ("Ministry of Defence",
     "https://www.gov.uk/government/organisations/ministry-of-defence.atom"),
    ("Prime Minister's Office, 10 Downing Street",
     "https://www.gov.uk/government/organisations/prime-ministers-office-10-downing-street.atom"),
    ("HM Treasury",
     "https://www.gov.uk/government/organisations/hm-treasury.atom"),
    ("Cabinet Office",
     "https://www.gov.uk/government/organisations/cabinet-office.atom"),
]
USER_AGENT = "Mozilla/5.0 iran-watcher (chris.moran@guardian.co.uk)"


def fetch(since: datetime) -> list[dict]:
    out: list[dict] = []
    for label, url in DEPARTMENTS:
        out.extend(_fetch_one(label, url, since))
    return out


def _fetch_one(label: str, url: str, since: datetime) -> list[dict]:
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
    r.raise_for_status()
    d = feedparser.parse(r.text)

    out = []
    for e in d.entries:
        pub = _parse_date(
            e.get("published")
            or e.get("updated")
            or _from_struct(e.get("published_parsed") or e.get("updated_parsed"))
        )
        if pub is None or pub < since:
            continue
        link = e.get("link") or ""
        title = (e.get("title") or "").strip()
        out.append({
            "id": f"govuk:{e.get('id') or link}",
            "source": "UK Government",
            "source_detail": label,
            "source_tier": 2,
            "category": "uk-govt",
            "published_at": pub.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": link,
            "summary": _strip_html(e.get("summary") or "")[:500],
            "details": {},
            "tags": ["uk-government"],
        })
    return out


def _from_struct(t):
    if not t:
        return None
    return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc).isoformat()


def _parse_date(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return s.astimezone(timezone.utc) if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
