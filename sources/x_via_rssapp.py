"""IDF and CENTCOM via X, surfaced through rss.app.

X (Twitter) doesn't expose a usable public scraping path any more, but
rss.app's free tier wraps any public X account in a JSON Feed for two
URLs per account. Chris set those up; the URLs below are the result.

Editorially these are the same provenance band as the US State Department
or UK gov.uk Atom — official-body broadcasts — so they sit at tier 2.
The content is partial in the same way every press-spox feed is partial
(the IDF will say its strikes succeeded; CENTCOM will say its blockade
is working) and the source-line makes the X-via-rss.app delivery mechanism
visible so the reader knows what they're reading.

Closes most of the tactical-military gap to ISW. ISW's 1 May report
cited "40+ Hezbollah infrastructure sites dismantled" and "45 commercial
vessels redirected" — both are now in our feed.

Free-tier risk: rss.app may throttle, paywall or rate-limit. The adapter
fails gracefully on any non-200 (one feed's failure doesn't take down
the other) and the diagnostics block records it.
"""

from datetime import datetime, timezone
import httpx

USER_AGENT = "Mozilla/5.0 iran-watcher (chris.moran@guardian.co.uk)"

# Channel handle -> feed config. Feed URLs are obscurity-only — anyone with
# them can fetch the data, but the underlying tweets are already public; only
# Chris's rss.app dashboard can change/delete the feed itself.
FEEDS = [
    {
        "url": "https://rss.app/feeds/v1.1/b6f6Wv6aVDczMew1.json",
        "handle": "@IDF",
        "source": "IDF",
        "source_detail": "Israel Defense Forces · X (via rss.app)",
        "category": "idf-x",
    },
    {
        "url": "https://rss.app/feeds/v1.1/gaCZVDmivtEgTH6P.json",
        "handle": "@CENTCOM",
        "source": "CENTCOM",
        "source_detail": "U.S. Central Command · X (via rss.app)",
        "category": "centcom-x",
    },
]


def fetch(since: datetime) -> list[dict]:
    out: list[dict] = []
    for feed_cfg in FEEDS:
        try:
            out.extend(_fetch_one(feed_cfg, since))
        except Exception as e:
            # One feed's failure shouldn't take down the other.
            print(f"  x_via_rssapp/{feed_cfg['handle']}: {e}")
    return out


def _fetch_one(cfg: dict, since: datetime) -> list[dict]:
    r = httpx.get(
        cfg["url"],
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    out = []
    for item in payload.get("items", []):
        published = _parse_dt(item.get("date_published"))
        if published is None or published < since:
            continue
        url = item.get("url") or item.get("external_url") or ""
        item_id = item.get("id") or url
        title = (item.get("title") or "").strip()
        text = (item.get("content_text") or _strip_html(item.get("content_html") or "")).strip()
        # rss.app sometimes emits the same content as both title and body;
        # if title is identical to text or is just the start of text, prefer
        # a synthesised title from the first ~100 chars for readability.
        if not title or title == text[:len(title)]:
            title = _short_title(text)

        out.append({
            "id": f"x_via_rssapp:{item_id}",
            "source": cfg["source"],
            "source_detail": cfg["source_detail"],
            "source_tier": 2,
            "category": cfg["category"],
            "published_at": published.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": url,
            "summary": text[:600],
            "details": {"handle": cfg["handle"]},
            "tags": ["x-twitter", "official-body", "claim"],
        })
    return out


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _strip_html(html: str) -> str:
    import re
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _short_title(text: str, n: int = 110) -> str:
    first_line = text.split("\n", 1)[0].strip()
    if len(first_line) <= n:
        return first_line
    return first_line[:n].rsplit(" ", 1)[0] + "…"
