"""UK Parliament — written questions and ministerial statements API.

Public, no key, free under the Open Parliament Licence.
https://questions-statements-api.parliament.uk
"""

from datetime import datetime
import httpx

QUESTIONS_ENDPOINT = "https://questions-statements-api.parliament.uk/api/writtenquestions/questions"
STATEMENTS_ENDPOINT = "https://questions-statements-api.parliament.uk/api/writtenstatements/statements"
PUBLIC_BASE = "https://questions-statements.parliament.uk"


def fetch(since: datetime) -> list[dict]:
    return _fetch_questions(since) + _fetch_statements(since)


def _fetch_questions(since: datetime) -> list[dict]:
    r = httpx.get(
        QUESTIONS_ENDPOINT,
        params={
            "searchTerm": "Iran",
            "tabledWhenFrom": since.date().isoformat(),
            "take": 100,
            "expandMember": True,
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    out = []
    for entry in payload.get("results", []):
        v = entry.get("value", entry)

        date_tabled = (v.get("dateTabled") or "")[:10]
        date_answered = (v.get("dateAnswered") or "")[:10]
        uin = v.get("uin", "")
        heading = v.get("heading") or "Iran (UK Parliament question)"
        question = (v.get("questionText") or "").strip()
        answer = (v.get("answerText") or "").strip()
        body = v.get("answeringBodyName") or "Government"
        url = f"{PUBLIC_BASE}/written-questions/detail/{date_tabled}/{uin}" if date_tabled and uin else PUBLIC_BASE

        if date_answered and answer:
            out.append({
                "id": f"ukparl-q-answered:{v['id']}",
                "source": f"UK Parliament — answer from {body}",
                "source_tier": 1,
                "published_at": date_answered + "T00:00:00Z",
                "title": f"Answered: {heading}",
                "url": url,
                "summary": _shorten(answer, 500),
                "tags": ["uk-parliament", "written-answer"],
            })

        if date_tabled:
            out.append({
                "id": f"ukparl-q-tabled:{v['id']}",
                "source": f"UK Parliament — written question to {body}",
                "source_tier": 1,
                "published_at": date_tabled + "T00:00:00Z",
                "title": f"Tabled: {heading}",
                "url": url,
                "summary": _shorten(question, 500),
                "tags": ["uk-parliament", "written-question"],
            })
    return out


def _fetch_statements(since: datetime) -> list[dict]:
    r = httpx.get(
        STATEMENTS_ENDPOINT,
        params={
            "searchTerm": "Iran",
            "madeWhenFrom": since.date().isoformat(),
            "take": 100,
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    out = []
    for entry in payload.get("results", []):
        v = entry.get("value", entry)
        date_made = (v.get("dateMade") or "")[:10]
        title = v.get("title") or "UK ministerial statement"
        body = v.get("answeringBodyName") or v.get("madeBy") or "UK Government"
        text = (v.get("text") or "").strip()
        uin = v.get("uin") or v.get("id", "")
        url = f"{PUBLIC_BASE}/written-statements/detail/{date_made}/{uin}" if date_made and uin else PUBLIC_BASE

        if not date_made:
            continue
        out.append({
            "id": f"ukparl-stmt:{v.get('id') or uin}",
            "source": f"UK Parliament — written statement ({body})",
            "source_tier": 1,
            "published_at": date_made + "T00:00:00Z",
            "title": title,
            "url": url,
            "summary": _shorten(text, 500),
            "tags": ["uk-parliament", "ministerial-statement"],
        })
    return out


def _shorten(s: str, n: int) -> str:
    s = s.strip()
    return s[:n] + ("…" if len(s) > n else "")
