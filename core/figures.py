"""Detect whether an event contains specific verifiable figures.

The "specific figures" flag answers one editorial question: is this card
something a correspondent would write FROM, or is it just context?

Cards with concrete numbers — "40+ Hezbollah sites", "45 vessels turned
around", "$344m frozen", "27% increase", "1.8 million rial per USD" —
are the writeable cards. Cards that are pure narrative or framing aren't.
The flag is surfaced as a small `[fig.]` marker on each card and as a
filter toggle that hides cards without figures, so the reader can scan
for the writeable layer in one click.

Detection is regex-based and deterministic — no model call. The patterns
favour false positives over false negatives: better to flag a card with
a borderline number than to miss a real figure. Editorial cost of a
false positive is low (one extra card visible); cost of a false negative
is a missed lead.
"""

from __future__ import annotations

import re

# Money: $344m, £1.2 billion, €5 million, US$10bn — handles common shapes.
_MONEY_RE = re.compile(
    r"(?:\$|£|€|US\$)\s?\d[\d,.]*\s?(?:m|bn|b|k|million|billion|trillion)?\b",
    re.I,
)

# Percentages: 27%, 27.5%, 100%
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%(?!\w)")

# Quantified counts of operational nouns. Two-or-more digit threshold
# eliminates the most common false positives (article numbers, single-digit
# counts that aren't really "figures" in the writeable sense).
_NOUNS = (
    "vessel|vessels|ship|ships|aircraft|aircrafts?|tank|tanks|"
    "site|sites|target|targets|launcher|launchers|tunnel|tunnels|"
    "weapon|weapons|missile|missiles|rocket|rockets|drone|drones|"
    "bomb|bombs|warhead|warheads|"
    "killed|dead|wounded|injured|casualties|fatalities|"
    "dismantled|destroyed|intercepted|fired|launched|struck|strikes?|"
    "attacks?|raids?|"
    "sanctions?|designations?|"
    "prisoners?|hostages?|detainees?|"
    "displaced|refugees?|"
    "soldiers?|troops?|fighters?|operatives?|terrorists?|militants?|"
    "incidents?"
)
_COUNT_RE = re.compile(
    rf"\b\d{{2,}}[\d,]*\+?\s+(?:{_NOUNS})\b",
    re.I,
)

# Physical units: 15km, 92 nm, 1,000 tonnes
_UNIT_RE = re.compile(
    r"\b\d+(?:[\.,]\d+)?\s?(?:km|kg|nm|miles?|tonnes?|tons?|kilometres?|kilometers?)\b",
    re.I,
)

# Large numerical anchors: "1.8 million rial", "5 billion euros", "200,000 displaced".
# Only fires when paired with a magnitude word — this is the "named figure"
# pattern (rial-to-USD rate, refugee count, military strength estimates).
_MAGNITUDE_RE = re.compile(
    r"\b\d+(?:[\.,]\d+)?\s+(?:million|billion|thousand)\b",
    re.I,
)

# Time / strike windows: "24-hour airstrike count", "in 24 hours", "every 48 hours"
_WINDOW_RE = re.compile(
    r"\b\d{1,3}\s?-?\s?hours?\b|\bin\s\d{1,3}\s?(?:hours?|hrs?)\b",
    re.I,
)


PATTERNS = [
    ("money", _MONEY_RE),
    ("percent", _PERCENT_RE),
    ("count", _COUNT_RE),
    ("unit", _UNIT_RE),
    ("magnitude", _MAGNITUDE_RE),
    ("window", _WINDOW_RE),
]


def detect(text: str) -> list[str]:
    """Return the list of distinct example figures matched in `text`.

    Empty list means no figures detected. Caller should treat as a boolean
    most of the time; the matches list is useful for a tooltip on the
    `[fig.]` marker showing what was matched.
    """
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for _kind, rx in PATTERNS:
        for m in rx.finditer(text):
            snippet = m.group(0).strip().lower()
            if snippet not in seen:
                seen.add(snippet)
                out.append(m.group(0).strip())
            if len(out) >= 4:  # don't bloat the tooltip — first few are enough
                return out
    return out


def annotate_event(event: dict) -> dict:
    """Mutate `event` in-place to add `has_figures` (bool) and, if present,
    `figures_examples` (list of up to 4 matched snippets). Returns the same
    dict for fluency."""
    blob = " ".join(
        s
        for s in (
            event.get("title_en") or event.get("title") or "",
            event.get("summary_en") or event.get("summary") or "",
        )
        if s
    )
    matches = detect(blob)
    event["has_figures"] = bool(matches)
    if matches:
        event["figures_examples"] = matches
    return event


def annotate_events(events: list[dict]) -> list[dict]:
    """Bulk version. Same in-place semantics; returns the same list."""
    for e in events:
        annotate_event(e)
    return events
