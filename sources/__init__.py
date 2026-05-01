"""Source adapters. Each module exposes `fetch(since: datetime) -> list[Event]`.

Event is a plain dict with the shape:

    {
        "id":           str,           # globally unique, stable across runs
        "source":       str,           # human-readable, e.g. "UN OCHA / ReliefWeb"
        "source_tier":  int,           # 1 = clean API, 2 = RSS, 3 = scraped
        "published_at": str,           # ISO 8601 UTC
        "title":        str,
        "url":          str,
        "summary":      str,           # short — first paragraph or API summary field
        "tags":         list[str],     # e.g. ["humanitarian", "nuclear"]
    }
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
