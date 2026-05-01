"""US Federal Register API adapter.

Public REST API, no key required. https://www.federalregister.gov/developers/documentation/api/v1
Covers executive orders, proclamations, agency rules, and crucially OFAC sanctions notices.
"""

from datetime import datetime
import httpx

ENDPOINT = "https://www.federalregister.gov/api/v1/documents.json"
USER_AGENT = "iran-watcher (chris.moran@guardian.co.uk)"


def fetch(since: datetime) -> list[dict]:
    r = httpx.get(
        ENDPOINT,
        params={
            "conditions[term]": "Iran",
            "conditions[publication_date][gte]": since.date().isoformat(),
            "order": "newest",
            "per_page": 100,
            "fields[]": [
                "title",
                "document_number",
                "publication_date",
                "html_url",
                "abstract",
                "type",
                "agencies",
                "presidential_document_number",
            ],
        },
        timeout=30,
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    payload = r.json()

    out = []
    for item in payload.get("results", []):
        agencies = ", ".join(a.get("name", "") for a in item.get("agencies", []) if a.get("name"))
        doc_type = item.get("type", "Document")
        source_label = "US Federal Register"
        if doc_type in ("Presidential Document", "Executive Order", "Proclamation"):
            source_label = "White House (Federal Register)"
        elif "Treasury" in agencies or "OFAC" in (item.get("title") or ""):
            source_label = "US Treasury / OFAC (Federal Register)"
        elif agencies:
            source_label = f"{agencies.split(',')[0].strip()} (Federal Register)"

        out.append({
            "id": f"fedreg:{item['document_number']}",
            "source": source_label,
            "source_tier": 1,
            "published_at": item["publication_date"] + "T00:00:00Z",
            "title": item["title"],
            "url": item["html_url"],
            "summary": (item.get("abstract") or "").strip(),
            "tags": _tags(doc_type, item.get("title", "")),
        })
    return out


def _tags(doc_type: str, title: str) -> list[str]:
    tags = []
    t = (title or "").lower()
    if doc_type in ("Executive Order", "Proclamation", "Presidential Document"):
        tags.append("executive-order")
    if "sanction" in t or "ofac" in t:
        tags.append("sanctions")
    if "nuclear" in t or "enrichment" in t:
        tags.append("nuclear")
    return tags or ["regulatory"]
