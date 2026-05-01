"""Translate non-English event titles and summaries to English.

Uses claude-haiku-4-5 with a structured-output schema so the response is
always parseable JSON. One bundled call per run regardless of how many
events need translating. Per-event cache on disk keyed by event id, so
the same Telegram post never gets translated twice.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
CACHE_FILE = ROOT / "data" / "translation_cache.json"

MODEL = "claude-haiku-4-5"
MAX_PER_CALL = 60          # cap a single API call's payload
TITLE_LIMIT_CHARS = 280
SUMMARY_LIMIT_CHARS = 600

SYSTEM_PROMPT = (
    "You are a translator working for a UK newsroom's Iran/Middle East tip-sheet. "
    "Translate the supplied items from their source language (typically Persian, "
    "Arabic, or Hebrew) into clear, idiomatic British English. "
    "RULES: "
    "(1) Translate faithfully — do not paraphrase, summarise, soften, or omit. "
    "(2) Do not add commentary, context, framing, or scare quotes that aren't in "
    "the original. "
    "(3) Preserve proper nouns and technical terms (e.g. IRGC, Sepah, Strait of "
    "Hormuz). "
    "(4) For social-media flourishes (emojis, hashtags, '@channel' tags) translate "
    "the surrounding text and drop the flourish. "
    "(5) If a title is just a teaser ('Watch: ...'), translate it literally. "
    "(6) Output the translation only — no notes, no caveats."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title_en": {"type": "string"},
                    "summary_en": {"type": "string"},
                },
                "required": ["id", "title_en", "summary_en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def translate_events(events: list[dict]) -> list[dict]:
    """Add `title_en` and `summary_en` to events whose source language isn't English.

    Mutates events in place AND returns them. Idempotent — re-running on the
    same events is a cache hit only.
    """
    cache = _load_cache()
    pending: list[dict] = []

    for e in events:
        if not _needs_translation(e):
            continue
        cached = cache.get(e["id"])
        if cached:
            e["title_en"] = cached["title_en"]
            e["summary_en"] = cached["summary_en"]
            continue
        pending.append(e)

    if not pending:
        return events

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            f"  translate: ANTHROPIC_API_KEY not set, skipping "
            f"({len(pending)} items would have been translated)",
            file=sys.stderr,
        )
        return events

    client = anthropic.Anthropic()
    n_translated = 0
    for batch in _chunks(pending, MAX_PER_CALL):
        try:
            results = _translate_batch(client, batch)
        except Exception as exc:  # don't let translation kill the run
            print(f"  translate: batch failed — {exc}", file=sys.stderr)
            continue
        for r in results:
            ev = next((e for e in batch if e["id"] == r["id"]), None)
            if not ev:
                continue
            ev["title_en"] = r["title_en"]
            ev["summary_en"] = r["summary_en"]
            cache[ev["id"]] = {"title_en": r["title_en"], "summary_en": r["summary_en"]}
            n_translated += 1

    if n_translated:
        _save_cache(cache)
    print(f"  translate: {n_translated} items translated, {len(events) - len(pending)} from cache",
          file=sys.stderr)
    return events


def _needs_translation(event: dict) -> bool:
    details = event.get("details") or {}
    lang = details.get("language")
    return lang in ("fa", "ar", "he")


def _translate_batch(client: anthropic.Anthropic, batch: list[dict]) -> list[dict]:
    items = [
        {
            "id": e["id"],
            "language": (e.get("details") or {}).get("language", "auto"),
            "title": (e.get("title") or "")[:TITLE_LIMIT_CHARS],
            "summary": (e.get("summary") or "")[:SUMMARY_LIMIT_CHARS],
        }
        for e in batch
    ]
    user_message = (
        "Translate every item below. Return the translations array in the same "
        "order, keeping the `id` field intact so we can match results. Translate "
        "both `title` and `summary` to English.\n\n"
        f"```json\n{json.dumps(items, ensure_ascii=False, indent=2)}\n```"
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    parsed = json.loads(text)
    return parsed.get("translations", [])


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
