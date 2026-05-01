"""Telegram public-channel adapter via t.me/s/ HTML preview.

Scrapes the public web preview rather than using the MTProto API, so no
phone number, no session file, no Guardian institutional sign-off needed.

Trade-off: only works for channels whose admins haven't disabled the
public web preview. Confirmed working at time of writing on:
  - rahbar_enghelab_ir  Khamenei's office (Iran's Supreme Leader)
  - iribnews            Iranian state broadcaster
  - defapress_ir        IRGC-affiliated defence press

Not working via this route (preview disabled or Telegram returning 500s):
  - idfonline / IDFFarsi / IDFArabic   IDF official
  - mmirleb                            Hezbollah
  - Tasnimnews                         Iranian state news (intermittent)

For those, MTProto via Telethon is the next step — separate work, and
for Hezbollah specifically a Guardian legal sign-off is needed independent
of access mechanism.

Items emit at tier 4: a regime-channel claim, not a verified fact. The
renderer styles tier-4 distinctly so the reader can never mistake a
Khamenei broadcast for a State Department designation.
"""

from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup

# Channel handle -> (display name, descriptor for source-line, language code)
CHANNELS = [
    ("rahbar_enghelab_ir", "Khamenei’s office", "Iran Supreme Leader · Telegram", "fa"),
    ("iribnews",           "IRIB",              "Iranian state broadcaster · Telegram", "fa"),
    ("defapress_ir",       "Defa Press",        "IRGC-affiliated defence press · Telegram", "fa"),
]
USER_AGENT = "Mozilla/5.0 iran-watcher (chris.moran@guardian.co.uk)"


def fetch(since: datetime) -> list[dict]:
    out: list[dict] = []
    for handle, display, descriptor, lang in CHANNELS:
        try:
            out.extend(_fetch_channel(handle, display, descriptor, lang, since))
        except Exception as e:
            # One channel's failure shouldn't take down the rest.
            print(f"  telegram/{handle}: {e}")
    return out


def _fetch_channel(handle: str, display: str, descriptor: str, lang: str, since: datetime) -> list[dict]:
    url = f"https://t.me/s/{handle}"
    r = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[dict] = []
    for msg in soup.select(".tgme_widget_message_wrap .tgme_widget_message"):
        post_id = msg.get("data-post", "")
        if not post_id or "/" not in post_id:
            continue
        time_el = msg.select_one(".tgme_widget_message_date time")
        iso = time_el.get("datetime") if time_el else None
        published = _parse_dt(iso)
        if published is None or published < since:
            continue

        text_el = msg.select_one(".tgme_widget_message_text")
        # The .tgme_widget_message_text div is the message body. It may
        # contain multiple of these (e.g. caption + author block); take
        # the first, which is the content.
        text = _clean_text(text_el)
        if not text:
            # Photos/videos with no caption render as "Please open Telegram"
            # — we still surface them so the editor sees the activity.
            text = "(media post — open in Telegram to view)"

        link = f"https://t.me/{post_id}"
        title = _title_from_text(text)

        out.append({
            "id": f"telegram:{post_id}",
            "source": "Regime channels",  # canonical source family for filter pill
            "source_detail": f"{display} — {descriptor}",
            "source_tier": 4,
            "category": "telegram-claim",
            "published_at": published.isoformat().replace("+00:00", "Z"),
            "title": title,
            "url": link,
            "summary": text[:600],
            "details": {
                "channel_handle": handle,
                "channel_display": display,
                "language": lang,
                "post_id": post_id,
            },
            "tags": ["telegram", "claim", lang],
        })
    return out


def _clean_text(el) -> str:
    if el is None:
        return ""
    # Telegram replaces newlines with <br>; convert before stripping.
    for br in el.find_all("br"):
        br.replace_with("\n")
    return el.get_text(separator=" ", strip=True)


def _title_from_text(text: str, n: int = 110) -> str:
    """Telegram posts have no title — synthesise one from the first sentence."""
    first_line = text.split("\n", 1)[0].strip()
    if len(first_line) <= n:
        return first_line
    return first_line[:n].rsplit(" ", 1)[0] + "…"


def _parse_dt(s):
    if not s:
        return None
    try:
        # Telegram emits ISO 8601 with timezone, e.g. "2026-05-01T16:02:46+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except ValueError:
        return None
