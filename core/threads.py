"""Synthesise the day's events into five themed threads.

One Opus 4.7 call per run. Adaptive thinking + medium effort. The
system prompt is strict about NOT editorialising — the model's job is
to cluster items and describe them, not to "make sense of" them. Each
thread carries a flag if it draws on tier-4 (regime-channel claim)
items so the renderer can show that visibly to the reader.
"""

from __future__ import annotations

import json
import os
import sys

import anthropic

MODEL = "claude-opus-4-7"
MAX_EVENTS = 80              # don't bloat the prompt past what's useful
THREAD_COUNT_TARGET = 5

SYSTEM_PROMPT = """\
You are an editorial assistant synthesising a UK newsroom's daily Iran / Middle
East tip-sheet. You will be given a flat list of events drawn from primary
governmental sources (UK Parliament, US State Department, OFAC sanctions
notices, IAEA, UN press, gov.uk Atom feeds), opposition media (Iran
International), and regime channels (Telegram from Khamenei's office, IRIB,
Defa Press — these are tier 4 claims, not facts).

Your job: cluster the items into FIVE thematic threads and produce, for each
thread, a short label and a two-sentence summary that names what happened.

HARD RULES:
1. NO interpretation, NO analysis, NO "this suggests…", NO "experts say…",
   NO "appears to indicate…", NO "could signal…". You are summarising what
   was reported, not assessing what it means.
2. NO editorial framing words like "amid", "as tensions rise", "in a
   significant escalation", "raising concerns". Stay flat and factual.
3. Each thread must reference at least two of the supplied event IDs in its
   `event_ids` array. Use the exact IDs from the input.
4. If a thread draws on any tier-4 (regime-channel) item, set
   `tier4_present` to true. Phrase any claim from a tier-4 source as a
   claim, not a fact ("Khamenei's office said…", "Defa Press posted…").
5. Each summary is exactly two sentences. The first names what happened;
   the second adds the most important specific detail (a named source, a
   named figure, a number, a date). Keep each sentence under 35 words.
6. Labels are short — 4 to 8 words. They describe the cluster ("Strait of
   Hormuz coalition firms up"), not the editorial spin.
7. If fewer than five distinct themes are genuinely present, return fewer
   than five threads. Do not invent themes to hit the count.
8. Do not include items that don't cluster — leave singletons out of the
   threads list rather than padding."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "threads": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Short cluster label, 4-8 words, descriptive not editorial."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Exactly two sentences. No editorialising."
                    },
                    "event_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of events grouped under this thread, exact strings from input."
                    },
                    "tier4_present": {
                        "type": "boolean",
                        "description": "True if any event in this thread is tier 4 (regime-channel claim)."
                    },
                },
                "required": ["label", "summary", "event_ids", "tier4_present"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["threads"],
    "additionalProperties": False,
}


def synthesise_threads(events: list[dict]) -> list[dict]:
    """Return a list of thread dicts. Empty list on any failure or missing key."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  threads: ANTHROPIC_API_KEY not set, skipping", file=sys.stderr)
        return []
    if len(events) < 6:
        # Not enough material to cluster meaningfully.
        print(f"  threads: only {len(events)} events, skipping synthesis", file=sys.stderr)
        return []

    payload = [_brief_event(e) for e in events[:MAX_EVENTS]]
    user_message = (
        f"Cluster the {len(payload)} events below into up to {THREAD_COUNT_TARGET} "
        "threads. Apply the editorial rules.\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```"
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        parsed = json.loads(text)
        threads = parsed.get("threads", [])
        print(f"  threads: synthesised {len(threads)} threads", file=sys.stderr)
        return threads
    except Exception as exc:
        print(f"  threads: synthesis failed — {exc}", file=sys.stderr)
        return []


def _brief_event(e: dict) -> dict:
    """Compact event shape for the synthesis prompt — only fields the model needs."""
    title = e.get("title_en") or e.get("title") or ""
    summary = e.get("summary_en") or e.get("summary") or ""
    return {
        "id": e["id"],
        "source": e.get("source") or "",
        "source_detail": e.get("source_detail") or "",
        "tier": e.get("source_tier") or 2,
        "published": (e.get("published_at") or "")[:16],
        "title": title[:200],
        "summary": summary[:400],
    }
