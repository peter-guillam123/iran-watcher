"""ReliefWeb API adapter — UN OCHA's humanitarian reporting platform.

Since 1 November 2025 ReliefWeb requires a pre-approved appname.
Register here:
    https://docs.google.com/forms/d/e/1FAIpQLScR5EE_SBhweLLg_2xMCnXNbT6md4zxqIB00OL0yZWyrqX_Nw/viewform
Set RELIEFWEB_APPNAME in the environment once approved.
"""

from datetime import datetime
import os
import httpx

APPNAME = os.environ.get("RELIEFWEB_APPNAME")
ENDPOINT = "https://api.reliefweb.int/v2/reports"


def fetch(since: datetime) -> list[dict]:
    if not APPNAME:
        raise RuntimeError(
            "RELIEFWEB_APPNAME not set — ReliefWeb v2 requires a pre-approved appname. "
            "See module docstring for the registration form."
        )
    # ReliefWeb's ISO 8601 parser rejects microsecond precision — it wants
    # second-precision timestamps. `2026-04-20T07:17:00.123456+00:00` is
    # rejected; `2026-04-20T07:17:00+00:00` is accepted. Strip microseconds.
    since_iso = since.replace(microsecond=0).isoformat()
    body = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "primary_country.iso3", "value": "irn"},
                {"field": "date.created", "value": {"from": since_iso}},
                # ReliefWeb publishes the same UN / ICRC / WHO releases in
                # English, French and Spanish. Without this filter the brief
                # gets the same situation report three times. English only.
                {"field": "language.code", "value": "en"},
            ],
        },
        "fields": {
            "include": ["title", "url", "date", "body-html", "source", "format"],
        },
        "sort": ["date.created:desc"],
        "limit": 100,
    }
    r = httpx.post(
        ENDPOINT,
        params={"appname": APPNAME},
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    out = []
    for item in payload.get("data", []):
        f = item["fields"]
        out.append({
            "id": f"reliefweb:{item['id']}",
            "source": "ReliefWeb",
            "source_detail": "UN OCHA",
            "source_tier": 1,
            "category": "reliefweb",
            "published_at": f["date"]["created"],
            "title": f["title"],
            "url": f.get("url") or f"https://reliefweb.int/node/{item['id']}",
            "summary": _short(f.get("body-html", "")),
            "details": {},
            "tags": ["humanitarian"],
        })
    return out


def _short(html: str, n: int = 400) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:n] + ("…" if len(text) > n else "")
