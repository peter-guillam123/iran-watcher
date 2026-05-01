"""Source adapters. Each module exposes `fetch(since: datetime) -> list[Event]`.

Event is a plain dict with the shape:

    {
        "id":            str,    # globally unique, stable across runs
        "source":        str,    # canonical source family — e.g. "UK Parliament",
                                 # "US State Department", "Iran International".
                                 # Used by the renderer to group filter pills.
        "source_detail": str,    # descriptive subsource for display under the title
                                 # — e.g. "FCDO (answer)", "Near East", "Lord Alton".
        "source_tier":   int,    # 1 = clean API, 2 = RSS, 3 = scraped/3rd-party
        "category":      str,    # event-type key for template selection — e.g.
                                 # "parliament-question", "executive-order",
                                 # "iran-news", "un-press". Categories starting
                                 # with "parliament-" get the rich Q&A layout.
        "published_at":  str,    # ISO 8601 UTC
        "title":         str,
        "url":           str,
        "summary":       str,    # short text — for cards and previews
        "details":       dict,   # optional structured fields (e.g. asking_member,
                                 # question_text, answer_text) for rich layouts.
                                 # Empty {} for events that don't need it.
        "tags":          list[str],
    }
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
