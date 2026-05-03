"""Run every source adapter, filter for Iran/Middle East, dedupe, write today's JSON."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import threads as _threads
from core import translate as _translate
from sources import bluesky, federal_register, gov_uk, iaea, iran_international, reliefweb, state_dept, telegram, uk_parliament, un_press, x_via_rssapp

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

# Iran beat keyword filter. Inclusive on purpose — the editor sifts for
# noise; missing items are invisible and worse. But not so inclusive that
# every IAEA Ukraine update or every Saudi-tagged story floods the brief:
# "iaea" alone is too broad (the IAEA is a nuclear watchdog, not just an
# Iran one), and bare "saudi" hits routine bilateral stories. The filter
# requires either an Iran-specific term or a Middle-East term anchored to
# something that signals Iran-relevance.
IRAN_TERMS = [
    "iran", "iranian", "tehran", "khamenei", "irgc", "revolutionary guard",
    "hezbollah", "houthi", "hamas", "yemen", "yemeni",
    "strait of hormuz", "persian gulf",
    "jcpoa", "snapback", "fordow", "natanz", "isfahan",
    "centcom", "mahan air",
]
# These are picked up only when paired with an Iran-relevant context word
# in the same item. We accept them on their own when prefixed by 'iran' or
# similar — the regex below handles that by always OR-ing IRAN_TERMS.
SECONDARY_TERMS = [
    "syria", "syrian", "bahrain", "kuwait", "oman", "qatar",
    "saudi arabia", "saudi-led", "uae", "emirates", "jordan",
    "iaea", "nuclear deal",
]

IRAN_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in IRAN_TERMS) + r")\b", re.I)
SECONDARY_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in SECONDARY_TERMS) + r")\b", re.I)


ADAPTERS = [
    ("federal_register", federal_register.fetch, False),  # already Iran-filtered server-side
    ("uk_parliament",    uk_parliament.fetch,    False),  # already Iran-filtered server-side
    ("un_press",         un_press.fetch,         True),   # global feed, filter locally
    ("iaea",             iaea.fetch,             True),   # global feed, filter locally
    ("state_dept",       state_dept.fetch,       True),   # global feeds, filter locally
    ("gov_uk",           gov_uk.fetch,           True),   # department feeds, filter locally
    ("iran_international", iran_international.fetch, False),  # all items already Iran-relevant
    ("telegram",         telegram.fetch,         False),  # regime channels — Iran-relevant by definition
    ("x_via_rssapp",     x_via_rssapp.fetch,     False),  # IDF + CENTCOM via rss.app — official military broadcasts during a live Iran/Hezbollah war, curated by definition. Local filter dropped IDF strike posts that said "southern Lebanon" without naming Hezbollah.
    ("bluesky",          bluesky.fetch,          True),   # Times of Israel + Jerusalem Post via Bluesky — global English news feeds, filter locally for Iran-relevance
    ("reliefweb",        reliefweb.fetch,        False),  # gated until appname registered
]


def main(
    window_days: int = 1,
    label: str | None = None,
    until: datetime | None = None,
) -> int:
    until_dt = until or datetime.now(timezone.utc)
    since = until_dt - timedelta(days=window_days)
    today = label or until_dt.date().isoformat()

    all_events: list[dict] = []
    diagnostics: list[dict] = []

    for name, fn, needs_local_filter in ADAPTERS:
        try:
            raw = fn(since)
            kept = [
                e for e in raw
                if (not needs_local_filter or _matches(e))
                and _within_until(e, until_dt)
            ]
            all_events.extend(kept)
            diagnostics.append({"source": name, "fetched": len(raw), "kept": len(kept), "ok": True})
            print(f"  {name}: fetched={len(raw)} kept={len(kept)}", file=sys.stderr)
        except Exception as e:
            diagnostics.append({"source": name, "ok": False, "error": str(e)})
            print(f"  {name}: ERROR {e}", file=sys.stderr)

    # Dedupe by id (last wins).
    by_id: dict[str, dict] = {}
    for e in all_events:
        by_id[e["id"]] = e
    events = sorted(by_id.values(), key=lambda e: e["published_at"], reverse=True)

    # Translation pass — adds title_en / summary_en to non-English events.
    # Cached on disk; no-op if ANTHROPIC_API_KEY is unset.
    events = _translate.translate_events(events)

    # Five-threads synthesis — one Opus call clustering the day into themes.
    # Empty list on missing key or thin volume.
    threads = _threads.synthesise_threads(events)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{today}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window_since": since.isoformat().replace("+00:00", "Z"),
        "window_until": until_dt.isoformat().replace("+00:00", "Z"),
        "diagnostics": diagnostics,
        "threads": threads,
        "events": events,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nwrote {out_path} ({len(events)} events, {len(threads)} threads)", file=sys.stderr)
    return 0


def _within_until(event: dict, until_dt: datetime) -> bool:
    """Drop events published after `until_dt`. Lets us reconstruct historical
    windows for like-for-like comparisons (e.g. matching the publication
    window of an ISW Iran Update)."""
    pub = event.get("published_at") or ""
    if not pub:
        return True
    try:
        dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
    except ValueError:
        return True
    return dt <= until_dt


def _matches(event: dict) -> bool:
    blob = " ".join([event.get("title") or "", event.get("summary") or ""])
    if IRAN_RE.search(blob):
        return True
    # A secondary term alone isn't enough; we need it AND an Iran-context
    # term, OR two secondary terms (which is a strong Middle-East-cluster
    # signal — e.g. "Saudi Arabia and Israel").
    sec_hits = SECONDARY_RE.findall(blob)
    return len(set(s.lower() for s in sec_hits)) >= 2


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    label = sys.argv[2] if len(sys.argv) > 2 else None
    until_arg = sys.argv[3] if len(sys.argv) > 3 else None
    until_dt = (
        datetime.fromisoformat(until_arg.replace("Z", "+00:00")) if until_arg else None
    )
    raise SystemExit(main(days, label, until_dt))
