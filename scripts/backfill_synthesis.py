"""Backfill translation + threads synthesis on existing data files.

Does NOT re-fetch events from sources — just runs the Claude API passes
over what we already have. Useful for retro-fitting the new threads /
translate layer onto historical archive days without rewriting their
event histories.

Re-fetching old days isn't useful in practice: t.me/s/ has no deep
archive (only the most recent ~20 posts per channel), and most other
sources would return slightly different results (UK Parliament edits,
State Dept rolls items off, etc.) so a re-fetch is closer to revisionism
than restoration.

Usage:
  uv run python scripts/backfill_synthesis.py            # all data files
  uv run python scripts/backfill_synthesis.py 2026-04-21 # specific stems

Requires ANTHROPIC_API_KEY in the environment (or repo secret).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core import threads as _threads  # noqa: E402
from core import translate as _translate  # noqa: E402

DATA_DIR = ROOT / "data"
SKIP = {"translation_cache"}


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set — backfill cannot run.", file=sys.stderr)
        print("Set it as a repo secret (Settings → Secrets → ANTHROPIC_API_KEY)", file=sys.stderr)
        return 1

    targets = set(sys.argv[1:])
    files = sorted(p for p in DATA_DIR.glob("*.json") if p.stem not in SKIP)
    if targets:
        files = [p for p in files if p.stem in targets]
        if not files:
            print(f"No matching files for: {sorted(targets)}", file=sys.stderr)
            return 1

    print(f"Backfilling {len(files)} file(s)…", file=sys.stderr)
    n_changed = 0

    for path in files:
        print(f"\n=== {path.stem} ===", file=sys.stderr)
        payload = json.loads(path.read_text())
        events = payload.get("events") or []
        if not events:
            print("  no events, skipping", file=sys.stderr)
            continue

        # Translation pass — adds title_en / summary_en where applicable.
        events = _translate.translate_events(events)

        # Figures detection — regex pass, runs after translation.
        from core import figures as _figures
        events = _figures.annotate_events(events)

        # Threads synthesis — produces a day_shape sentence plus up to
        # five (or seven on dense days) themed threads.
        synthesis = _threads.synthesise_threads(events)
        threads_list = synthesis.get("threads", [])
        day_shape = synthesis.get("day_shape", "")

        payload["events"] = events
        payload["threads"] = threads_list
        payload["day_shape"] = day_shape
        # Stamp the backfill so we know when each file was synthesised.
        payload["synthesised_at"] = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        n_changed += 1
        print(f"  wrote {len(events)} events, {len(threads_list)} threads", file=sys.stderr)

    print(f"\nBackfill complete: {n_changed} file(s) updated.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
