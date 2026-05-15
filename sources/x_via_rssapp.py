"""Iran-beat X accounts surfaced through rss.app.

X (Twitter) doesn't expose a usable public scraping path any more, but
rss.app wraps any public X account in a JSON Feed. Chris set the feeds
up on his rss.app account; the URLs below are the result.

Current accounts:
  - @IDF             — Israel Defense Forces (English)        official-body
  - @CENTCOM         — US Central Command                     official-body
  - @AvichayAdraee   — IDF Arabic spokesperson (Arabic)       official-body
  - @manniefabian    — Times of Israel military correspondent journalist

Editorially the four official-body accounts (IDF / CENTCOM / Adraee)
sit in the same provenance band as the US State Department or UK
gov.uk Atom — tier 2 broadcast layer. Manni Fabian is tier 2 too but
sits in the document zone (he's a journalist, not a spokesperson, and
the renderer treats the broadcast clustering as official-body only).

Arabic items (Adraee) get details.language = "ar" so the translation
pass picks them up and produces English title_en / summary_en. The
"Translated · Arabic" badge surfaces this on the rendered card.

Free-tier risk: rss.app may throttle, paywall or rate-limit. The
adapter fails gracefully on any non-200 (one feed's failure doesn't
take down the others) and the diagnostics block records it.
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
        "language": None,  # English
    },
    {
        "url": "https://rss.app/feeds/v1.1/gaCZVDmivtEgTH6P.json",
        "handle": "@CENTCOM",
        "source": "CENTCOM",
        "source_detail": "U.S. Central Command · X (via rss.app)",
        "category": "centcom-x",
        "language": None,  # English
    },
    {
        # IDF Arabic spokesperson — the IDF's voice to the Arab world.
        # Often more operationally specific than the English account,
        # frequently ahead on strike confirmations and evacuation
        # warnings to Lebanese / Syrian / Gazan civilians. Arabic text;
        # the translation pass picks it up because language = "ar".
        "url": "https://rss.app/feeds/v1.1/xSmJQT3k8F2k3jKo.json",
        "handle": "@AvichayAdraee",
        "source": "Avichay Adraee",
        "source_detail": "IDF Arabic spokesperson · X (via rss.app)",
        "category": "idf-arabic-x",
        "language": "ar",
    },
    {
        # Times of Israel's military correspondent. The specific
        # reporter ISW cites in footnotes for IDF strike counts and
        # named-commander operations. Has a Bluesky account that's
        # dormant since July 2025 — lives on X.
        "url": "https://rss.app/feeds/v1.1/iQSgdrj6tT64Hlig.json",
        "handle": "@manniefabian",
        "source": "Manni Fabian",
        "source_detail": "Times of Israel · military correspondent · X (via rss.app)",
        "category": "manniefabian-x",
        "language": None,  # English
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

        details = {"handle": cfg["handle"]}
        if cfg.get("language"):
            details["language"] = cfg["language"]

        # Journalist accounts (Manni Fabian) are tier 2 but editorially
        # different from official-body broadcasts (IDF / CENTCOM /
        # Adraee). The tags drive whether they end up in the military-
        # spokes broadcast cluster on the rendered page.
        is_official_body = cfg["category"] != "manniefabian-x"
        tags = ["x-twitter"]
        if is_official_body:
            tags += ["official-body", "claim"]
        else:
            tags += ["journalist"]

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
            "details": details,
            "tags": tags,
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
