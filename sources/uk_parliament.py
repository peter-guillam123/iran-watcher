"""UK Parliament — written questions and ministerial statements API.

Public OpenAPI under the Open Parliament Licence.
https://questions-statements-api.parliament.uk

Each question emits up to two events:
  - "tabled" — the act of asking, on the date tabled
  - "answered" — the substantive minister's reply, on the date answered

We populate `details` with member names, party, house, and the full
question and answer text so the renderer can show the full Q&A rather
than a truncated headline.

Member names come from a second API (members-api.parliament.uk),
looked up lazily and cached for the run.
"""

from datetime import datetime
import httpx

QUESTIONS_ENDPOINT = "https://questions-statements-api.parliament.uk/api/writtenquestions/questions"
STATEMENTS_ENDPOINT = "https://questions-statements-api.parliament.uk/api/writtenstatements/statements"
MEMBERS_ENDPOINT = "https://members-api.parliament.uk/api/Members/{id}"
PUBLIC_BASE = "https://questions-statements.parliament.uk"

_MEMBER_CACHE: dict[int, dict] = {}


def fetch(since: datetime) -> list[dict]:
    return _fetch_questions(since) + _fetch_statements(since)


def _fetch_questions(since: datetime) -> list[dict]:
    r = httpx.get(
        QUESTIONS_ENDPOINT,
        params={
            "searchTerm": "Iran",
            "tabledWhenFrom": since.date().isoformat(),
            "take": 100,
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    out: list[dict] = []
    for entry in payload.get("results", []):
        v = entry.get("value", entry)

        date_tabled = (v.get("dateTabled") or "")[:10]
        date_answered = (v.get("dateAnswered") or "")[:10]
        uin = v.get("uin", "")
        heading = v.get("heading") or "Iran (UK Parliament question)"
        question_text = (v.get("questionText") or "").strip()
        answer_text = (v.get("answerText") or "").strip()
        department = v.get("answeringBodyName") or "Government"
        url = (
            f"{PUBLIC_BASE}/written-questions/detail/{date_tabled}/{uin}"
            if date_tabled and uin
            else PUBLIC_BASE
        )
        asking = _member(v.get("askingMemberId"))
        answering = _member(v.get("answeringMemberId"))

        details_base = {
            "asking_member": asking,
            "answering_member": answering,
            "department": department,
            "date_tabled": date_tabled,
            "date_answered": date_answered or None,
            "question_text": question_text,
            "answer_text": answer_text,
            "uin": uin,
            "house": v.get("house"),
        }

        if date_answered and answer_text:
            out.append({
                "id": f"ukparl-q-answered:{v['id']}",
                "source": "UK Parliament",
                "source_detail": f"{department} — answer to {_member_short(asking)}",
                "source_tier": 1,
                "category": "parliament-answer",
                "published_at": date_answered + "T00:00:00Z",
                "title": heading,
                "url": url,
                "summary": _shorten(answer_text, 280),
                "details": details_base,
                "tags": ["uk-parliament", "written-answer"],
            })

        if date_tabled:
            out.append({
                "id": f"ukparl-q-tabled:{v['id']}",
                "source": "UK Parliament",
                "source_detail": f"{_member_short(asking)} → {department}",
                "source_tier": 1,
                "category": "parliament-question",
                "published_at": date_tabled + "T00:00:00Z",
                "title": heading,
                "url": url,
                "summary": _shorten(question_text, 280),
                "details": details_base,
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
        body = v.get("answeringBodyName") or "UK Government"
        text = (v.get("text") or "").strip()
        uin = v.get("uin") or v.get("id", "")
        url = (
            f"{PUBLIC_BASE}/written-statements/detail/{date_made}/{uin}"
            if date_made and uin
            else PUBLIC_BASE
        )
        member = _member(v.get("memberId") or v.get("madeByMemberId"))

        if not date_made:
            continue
        out.append({
            "id": f"ukparl-stmt:{v.get('id') or uin}",
            "source": "UK Parliament",
            "source_detail": f"Ministerial statement — {body}",
            "source_tier": 1,
            "category": "parliament-statement",
            "published_at": date_made + "T00:00:00Z",
            "title": title,
            "url": url,
            "summary": _shorten(text, 280),
            "details": {
                "made_by": member,
                "department": body,
                "date_made": date_made,
                "text": text,
            },
            "tags": ["uk-parliament", "ministerial-statement"],
        })
    return out


def _member(member_id) -> dict | None:
    """Look up a member by id; returns {name, party, house}. Cached."""
    if not member_id:
        return None
    if member_id in _MEMBER_CACHE:
        return _MEMBER_CACHE[member_id]
    try:
        r = httpx.get(MEMBERS_ENDPOINT.format(id=member_id), timeout=15)
        if r.status_code != 200:
            _MEMBER_CACHE[member_id] = None
            return None
        v = (r.json() or {}).get("value", {})
        party = (v.get("latestParty") or {}).get("name")
        house_id = (v.get("latestHouseMembership") or {}).get("house")
        house = "Lords" if house_id == 2 else ("Commons" if house_id == 1 else None)
        info = {
            "id": member_id,
            "name": v.get("nameDisplayAs") or v.get("nameFullTitle") or f"Member #{member_id}",
            "party": party,
            "house": house,
        }
    except Exception:
        info = None
    _MEMBER_CACHE[member_id] = info
    return info


def _member_short(m: dict | None) -> str:
    if not m:
        return "(unknown member)"
    party = m.get("party")
    return f"{m['name']} ({party})" if party else m["name"]


def _shorten(s: str, n: int) -> str:
    s = s.strip()
    return s[:n] + ("…" if len(s) > n else "")
