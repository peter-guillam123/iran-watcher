"""Israeli English press via Bluesky's public AT Protocol.

Times of Israel and the Jerusalem Post both run active Bluesky accounts
that auto-post their English-language headlines with an external embed
linking back to the article. The AT Protocol exposes a fully public,
unauthenticated read API — `app.bsky.feed.getAuthorFeed` returns JSON
without an API key, without a free-tier slot, and without a third-party
scraper sitting in the middle. Better than the X-via-rss.app path on
every dimension.

Editorially these are the English Israeli newspaper layer — solid daily
coverage of Iran/Lebanon/Gaza from an Israeli desk, in English, fast.
They sit at tier 2, alongside State Department or gov.uk Atom.

What this DOESN'T close: the Hebrew tactical/operational reporting that
ISW pulls from. Mako, YNet (Hebrew), Channel 12 and KAN aren't on
Bluesky in any active form. The named OSINT/Hebrew-press reporters
(Manni Fabian, Barak Ravid, Yossi Melman) all created BS accounts in
2024 and have effectively stopped posting there. That gap stays open
and the About page is honest about it.

Both feeds are global English-language news, so the local Iran keyword
filter applies in collect.py (needs_local_filter=True) — unlike IDF/
CENTCOM which are inherently on-beat during a live Iran/Hezbollah war.
"""

from datetime import datetime, timezone
import re
import httpx

USER_AGENT = "Mozilla/5.0 iran-watcher (chris.moran@guardian.co.uk)"
PUBLIC_API = "https://public.api.bsky.app/xrpc"

ACCOUNTS = [
    {
        "handle": "timesofisrael.com",
        "source": "Times of Israel",
        "source_detail": "Times of Israel · Bluesky",
        "category": "toi-bsky",
    },
    {
        "handle": "thejerusalempost.bsky.social",
        "source": "Jerusalem Post",
        "source_detail": "The Jerusalem Post · Bluesky",
        "category": "jpost-bsky",
    },
]

URL_RE = re.compile(r"https?://\S+")


def fetch(since: datetime) -> list[dict]:
    out: list[dict] = []
    for acct in ACCOUNTS:
        try:
            out.extend(_fetch_account(acct, since))
        except Exception as e:
            # One account's failure shouldn't take down the rest.
            print(f"  bluesky/{acct['handle']}: {e}")
    return out


def _fetch_account(acct: dict, since: datetime) -> list[dict]:
    r = httpx.get(
        f"{PUBLIC_API}/app.bsky.feed.getAuthorFeed",
        params={"actor": acct["handle"], "limit": 100},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    r.raise_for_status()
    feed = r.json().get("feed", [])

    out: list[dict] = []
    for item in feed:
        post = item.get("post") or {}
        record = post.get("record") or {}
        # Skip reposts (the parent feed item lacks a `record.text` for those)
        # and reply chains where the post being shown isn't the outlet's own.
        if record.get("$type") != "app.bsky.feed.post":
            continue

        published = _parse_dt(record.get("createdAt"))
        if published is None or published < since:
            continue

        text = (record.get("text") or "").strip()
        # Most outlet posts append a t.co-style URL after the headline.
        # Strip URLs from the visible text — we'll surface the article
        # URL separately via the external embed.
        text_clean = URL_RE.sub("", text).strip()

        # Article URL: prefer the external embed (the actual ToI/JPost
        # article link), fall back to the Bluesky post permalink.
        embed = record.get("embed") or {}
        article_url = _extract_external(embed) or _bsky_web_url(acct["handle"], post.get("uri", ""))

        title = _title_from_text(text_clean)

        out.append({
            "id": f"bluesky:{post.get('uri','')}",
            "source": acct["source"],
            "source_detail": acct["source_detail"],
            "source_tier": 2,
            "category": acct["category"],
            "published_at": published.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": article_url,
            "summary": text_clean[:600],
            "details": {"handle": acct["handle"]},
            "tags": ["bluesky", "israeli-press", "english"],
        })
    return out


def _extract_external(embed: dict) -> str:
    """Pull the article URL out of a Bluesky post's embed, if present.

    News outlet posts almost always carry an `app.bsky.embed.external`
    block containing the source article URL. Posts with only an image
    embed (e.g. quote cards, live-update screenshots) don't have one
    and fall back to the Bluesky permalink.
    """
    et = embed.get("$type", "")
    if et == "app.bsky.embed.external":
        return embed.get("external", {}).get("uri", "")
    if et == "app.bsky.embed.recordWithMedia":
        return embed.get("media", {}).get("external", {}).get("uri", "")
    return ""


def _bsky_web_url(handle: str, uri: str) -> str:
    """Convert an at:// URI to its bsky.app web permalink.

    URI looks like at://did:plc:.../app.bsky.feed.post/{rkey}; we need
    the rkey at the end and the handle the post was authored under.
    """
    if not uri:
        return ""
    rkey = uri.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _title_from_text(text: str, n: int = 140) -> str:
    """Posts have no title — synthesise one from the first sentence."""
    first_line = text.split("\n", 1)[0].strip()
    if len(first_line) <= n:
        return first_line
    return first_line[:n].rsplit(" ", 1)[0] + "…"


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None
