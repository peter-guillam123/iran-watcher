"""Run every source adapter, filter for Iran/Middle East, dedupe, write today's JSON."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sources import federal_register, reliefweb, uk_parliament, un_press

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"

# Iran beat keyword filter. Inclusive on purpose — the editor sifts for
# noise; missing items are invisible and worse.
KEYWORDS = [
    "iran", "iranian", "tehran", "khamenei", "irgc", "revolutionary guard",
    "hezbollah", "houthi", "hamas", "yemen", "syria", "syrian",
    "strait of hormuz", "persian gulf",
    "bahrain", "kuwait", "oman", "qatar", "saudi", "uae", "emirates", "jordan",
    "iaea", "nuclear deal", "jcpoa", "snapback", "fordow", "natanz", "isfahan",
    "centcom",
]
KEYWORD_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in KEYWORDS) + r")\b", re.I)


ADAPTERS = [
    ("federal_register", federal_register.fetch, False),  # already Iran-filtered server-side
    ("uk_parliament",    uk_parliament.fetch,    False),  # already Iran-filtered server-side
    ("un_press",         un_press.fetch,         True),   # global feed, filter locally
    ("reliefweb",        reliefweb.fetch,        False),  # gated until appname registered
]


def main(window_days: int = 1) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    today = datetime.now(timezone.utc).date().isoformat()

    all_events: list[dict] = []
    diagnostics: list[dict] = []

    for name, fn, needs_local_filter in ADAPTERS:
        try:
            raw = fn(since)
            kept = [e for e in raw if not needs_local_filter or _matches(e)]
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

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{today}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "window_since": since.isoformat().replace("+00:00", "Z"),
        "window_until": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "diagnostics": diagnostics,
        "events": events,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\nwrote {out_path} ({len(events)} events)", file=sys.stderr)
    return 0


def _matches(event: dict) -> bool:
    blob = " ".join([event.get("title") or "", event.get("summary") or ""])
    return bool(KEYWORD_RE.search(blob))


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    raise SystemExit(main(days))
