"""Grounded AI drafts. The model may only use profile + CV + opportunity text."""

from __future__ import annotations

import json
import logging
import re

import requests

from config import Config
from workdey.models import Match, Opportunity, Profile
from workdey.timeutil import utcnow

log = logging.getLogger("workdey.llm")

SYSTEM = """You are WorkDey Apply Assist. You draft job applications for Nigerian and African job seekers.

HARD RULES:
- Use ONLY facts in PROFILE, CV, and OPPORTUNITY. Never invent employers, dates, degrees, NYSC dates, or certifications.
- If a fact is missing, omit it. Do not guess.
- If the opportunity is not actually a job or looks like a scam, say so in one sentence and refuse to draft an application.
- Language: reply in the language of the post (English or light Nigerian pidgin-leaning English if the post is informal). Cover letters stay clear professional English unless asked.
- Length: Reply 40–90 words. Cover letter ≤ 280 words. CV revamp keeps the user's real history, reordered toward the post.
- Nigerian context is expected: NYSC, HND/BSc, remote-Nigeria, Lagos/Abuja/PH, "DM for pitch".
- Output JSON only, no markdown fences.
"""


def _pack(profile: Profile, opp: Opportunity, note: str, kind: str) -> str:
    return json.dumps(
        {
            "kind": kind,
            "note": note,
            "source": opp.source,
            "opportunity": {
                "title": opp.title_guess,
                "author": opp.author_name or opp.author_handle,
                "url": opp.external_url,
                "location": opp.location_guess,
                "classification": opp.classification,
                "scam_risk": opp.scam_risk,
                "body": (opp.body or "")[:2500],
            },
            "profile": {
                "name": profile.user.name if profile.user else "",
                "skills": profile.skills_tags,
                "skills_text": profile.skills_text,
                "education": profile.education,
                "years": profile.years_experience,
                "target_roles": profile.target_roles,
                "locations": profile.locations,
                "summary": profile.summary,
                "cv_excerpt": (profile.cv_text or "")[:3500],
            },
        }
    )


def _schema_hint(kind: str, source: str) -> str:
    if kind == "reply":
        tone = "casual WhatsApp/DM style" if source in {"x", "instagram"} else "short professional note"
        return f'Return {{"body": string, "facts_used": [string]}}. Draft a {tone} reply, 40-90 words.'
    if kind == "cover":
        return 'Return {"body": string, "facts_used": [string]}. One-page cover letter, ≤280 words, professional English.'
    return (
        'Return {"body": string, "facts_used": [string]}. A CV revamp as plain text sections '
        "(Name, Summary, Skills, Experience, Education). Same facts, reordered toward the post. Never invent jobs."
    )


def generate(profile: Profile, match: Match, kind: str, note: str = "") -> dict:
    opp = match.opportunity
    if opp.classification in {"not_a_job", "likely_scam"} or opp.scam_risk >= 0.6:
        return {
            "body": "This does not look like a safe, real opening. WorkDey will not draft an application. Mark it as spam if it feels off.",
            "facts_used": [],
            "refused": True,
        }
    if Config.GROQ_API_KEY:
        try:
            return _groq(profile, opp, kind, note)
        except Exception as exc:
            log.warning("groq failed, falling back: %s", exc)
    return _fallback(profile, opp, kind)


def _groq(profile: Profile, opp: Opportunity, kind: str, note: str) -> dict:
    user = _schema_hint(kind, opp.source) + "\n\nINPUT:\n" + _pack(profile, opp, note, kind)
    res = requests.post(
        f"{Config.GROQ_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {Config.GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": Config.GROQ_MODEL,
            "temperature": 0.4,
            "max_tokens": 900,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    if not res.ok:
        raise RuntimeError(f"Groq {res.status_code}: {res.text[:240]}")
    text = (res.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    parsed = _parse_json(text)
    body = (parsed.get("body") or text).strip()
    facts = parsed.get("facts_used") or []
    if not isinstance(facts, list):
        facts = []
    return {"body": body, "facts_used": [str(f)[:120] for f in facts[:12]], "refused": False}


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
        return {}


def _fallback(profile: Profile, opp: Opportunity, kind: str) -> dict:
    name = (profile.user.name if profile.user else "") or "I"
    role = (profile.target_roles or [profile.skills_tags[:1] and profile.skills_tags[0] or "the role"])[0]
    skills = ", ".join((profile.skills_tags or [])[:5]) or "the skills on my profile"
    loc = (profile.locations or [""])[0]
    title = opp.title_guess or "this opening"
    author = opp.author_name or opp.author_handle or "the team"
    facts = [f for f in [role, *(profile.skills_tags or [])[:4], profile.education, loc] if f]

    if kind == "reply" and opp.source in {"x", "instagram"}:
        body = (
            f"Hi {author.split()[0] if author else 'there'}, I saw the {title} post. "
            f"I'm {name}, a {role} with {skills}. "
            f"{'Based in ' + loc + '. ' if loc else ''}"
            f"Happy to DM my CV or jump on a quick call this week. Thanks."
        )
    elif kind == "reply":
        body = (
            f"Hello {author},\n\nI am writing about the {title} opening. "
            f"I am {name}, a {role} ({profile.years_experience} years) with {skills}. "
            f"{profile.education + '. ' if profile.education else ''}"
            f"I would welcome the chance to share a short CV. Thank you."
        )
    elif kind == "cover":
        body = (
            f"Dear Hiring Team at {author},\n\n"
            f"I am applying for the {title} role. I am {name}, a {role} with "
            f"{profile.years_experience} years around {skills}. "
            f"{profile.summary or 'I work carefully, communicate clearly, and ship.'} "
            f"{profile.education + '. ' if profile.education else ''}"
            f"{'I am based in ' + loc + ' and open to remote-Nigeria work. ' if loc else ''}"
            f"I have attached a tightened CV. I would be glad to walk you through a recent piece of work.\n\n"
            f"Kind regards,\n{name}"
        )
    else:
        exp = profile.summary or "Results-focused professional."
        skill_line = ", ".join(profile.skills_tags or []) or skills
        body = (
            f"{name}\n{role} · {loc or 'Nigeria'}\n\n"
            f"SUMMARY\n{exp}\n\n"
            f"SKILLS\n{skill_line}\n\n"
            f"EXPERIENCE\n{profile.years_experience} years · tailored toward {title} at {author}. "
            f"Facts taken from the uploaded CV only — add bullet points from real roles before sending.\n\n"
            f"EDUCATION\n{profile.education or 'Add your HND/BSc and NYSC here.'}\n"
        )
    return {
        "body": body.strip(),
        "facts_used": facts,
        "refused": False,
        "fallback": True,
    }
