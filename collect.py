"""Run every source adapter, filter for Iran/Middle East, dedupe, write today's JSON."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import figures as _figures
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
    # War-theatre primary names — added when Manni Fabian's filter started
    # dropping on-beat Lebanon/Gaza coverage (PIJ commander killed in
    # Lebanon, Israeli Navy intercepting Gaza-bound activist boats).
    # These were originally excluded so the IDF X feed wouldn't dilute,
    # but IDF/CENTCOM/Adraee bypass the filter at the adapter level
    # anyway — so adding these here only catches journalist X content
    # and Bluesky press coverage on the same beat.
    "lebanon", "lebanese", "gaza", "gazan",
    "islamic jihad", "pij",
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
    ("x_via_rssapp",     x_via_rssapp.fetch,     False),  # IDF / CENTCOM / Adraee official-body broadcasts skip the filter (curated by definition during the live Iran/Hezbollah war). Journalist accounts on this adapter (Manni Fabian) get force-filtered below — they post off-beat content (Eurovision retweets, internal Israeli politics) the filter should drop.
    ("bluesky",          bluesky.fetch,          True),   # Times of Israel + Jerusalem Post + Tanker Trackers via Bluesky — global feeds, filter locally for Iran-relevance
    ("reliefweb",        reliefweb.fetch,        False),  # tier 1, server-side Iran-only filter
]

# Sources within an otherwise-unfiltered adapter that DO need the Iran
# filter applied to them — used to drop off-beat content from journalist
# X accounts (e.g. Manni Fabian retweeting Eurovision coverage) without
# also dropping IDF / CENTCOM / Adraee strike confirmations which mention
# "southern Lebanon" but not "Hezbollah" by name.
FORCE_FILTER_SOURCES = {"Manni Fabian"}


def main(
    window_days: int = 1,
    label: str | None = None,
    until: datetime | None = None,
    edition: str | None = None,
) -> int:
    """Collect events, run translation + figures + threads passes, write JSON.

    `edition` switches between two daily editions:
      - "morning"  → 24h window back from `until`. File: data/{date}-morning.json
      - "evening"  → window starts at today 05:00 UTC ("since the morning
                     brief"). File: data/{date}-evening.json
      - None       → legacy single-edition behaviour. File: data/{date}.json
                     Used by historical comparisons and matched-window runs.
    """
    until_dt = until or datetime.now(timezone.utc)

    if edition == "evening":
        # Evening window starts at 05:00 UTC today — slightly before the
        # morning run's 05:30 UTC fire time, so we catch any items that
        # published in the gap. The evening brief is a "since this morning"
        # delta, not a full 24h re-read.
        since = until_dt.replace(hour=5, minute=0, second=0, microsecond=0)
        if since > until_dt:
            # Edge case: until_dt is before 05:00 UTC (manual run early in
            # the day). Fall back to morning window so we have something.
            since = until_dt - timedelta(days=window_days)
    else:
        since = until_dt - timedelta(days=window_days)

    date_label = label or until_dt.date().isoformat()
    if edition in ("morning", "evening"):
        out_stem = f"{date_label}-{edition}"
    else:
        out_stem = date_label

    all_events: list[dict] = []
    diagnostics: list[dict] = []

    for name, fn, needs_local_filter in ADAPTERS:
        try:
            raw = fn(since)
            kept = []
            for e in raw:
                if not _within_until(e, until_dt):
                    continue
                # Adapter-level filter (skipped for already-Iran-filtered
                # feeds like federal_register, telegram, etc.)
                needs_filter = needs_local_filter
                # Per-source override: certain journalist accounts within
                # otherwise-unfiltered adapters need the keyword filter
                # applied to drop their off-beat content.
                if e.get("source") in FORCE_FILTER_SOURCES:
                    needs_filter = True
                if needs_filter and not _matches(e):
                    continue
                kept.append(e)
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

    # Figures detection — regex pass, deterministic, runs after translation
    # so we can flag figures on the English version of Persian/Arabic posts.
    # Adds has_figures (bool) and figures_examples (list) to each event.
    events = _figures.annotate_events(events)

    # Threads synthesis — one Opus call producing both a day_shape line
    # and up to 5 (or 7 on dense days) themed threads. Empty result on
    # missing key or thin volume.
    synthesis = _threads.synthesise_threads(events)
    threads = synthesis.get("threads", [])
    day_shape = synthesis.get("day_shape", "")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{out_stem}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window_since": since.isoformat().replace("+00:00", "Z"),
        "window_until": until_dt.isoformat().replace("+00:00", "Z"),
        "edition": edition,
        "diagnostics": diagnostics,
        "day_shape": day_shape,
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
    import os
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    label = sys.argv[2] if len(sys.argv) > 2 else None
    until_arg = sys.argv[3] if len(sys.argv) > 3 else None
    edition_arg = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("EDITION") or None
    if edition_arg in ("", "none", "None"):
        edition_arg = None
    until_dt = (
        datetime.fromisoformat(until_arg.replace("Z", "+00:00")) if until_arg else None
    )
    raise SystemExit(main(days, label, until_dt, edition_arg))
