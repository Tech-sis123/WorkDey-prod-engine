"""Profile ↔ opportunity scorer. Related-to-the-profile, not perfect ranking."""

from __future__ import annotations

from datetime import datetime, timezone

from workdey.models import Opportunity, Profile
from workdey.services.textsim import cosine, overlap, vector
from workdey.timeutil import to_utc, utcnow

INTERN_RE = ("intern", "internship", "nysc only", "corper only", "siwes")


def score(profile: Profile, opp: Opportunity) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if opp.classification == "not_a_job" or opp.killed:
        return 0.0, []
    if opp.scam_risk >= 0.55:
        return 0.0, []
    if opp.job_confidence < 0.4 and opp.source != "workdey":
        return 0.0, []

    blob = f"{opp.title_guess} {opp.body} {opp.location_guess}"
    profile_blob = " ".join(
        [
            " ".join(profile.skills_tags or []),
            profile.skills_text or "",
            " ".join(profile.target_roles or []),
            profile.summary or "",
            (profile.cv_text or "")[:2500],
            profile.education or "",
        ]
    )

    sim = cosine(vector(profile_blob), vector(blob))
    skills = overlap(list(profile.skills_tags or []), blob)
    roles = overlap(list(profile.target_roles or []), blob)

    loc_boost = 0.0
    locs = [l.lower() for l in (profile.locations or [])]
    oloc = (opp.location_guess or "").lower()
    if locs:
        if any(l in oloc or l in blob.lower() for l in locs):
            loc_boost = 0.12
            reasons.append(f"{opp.location_guess or locs[0]} lines up with where you want to work.")
        elif oloc and oloc not in {"remote", "nigeria"} and not any(
            x in oloc for x in ("nigeria", "lagos", "abuja", "remote")
        ):
            loc_boost = -0.08
        if "remote" in oloc or "remote" in blob.lower():
            loc_boost = max(loc_boost, 0.06)

    if profile.work_type == "full-time" and opp.classification == "gig":
        loc_boost -= 0.1
    if profile.work_type == "gig" and opp.classification == "job" and opp.employment_type_guess == "full-time":
        loc_boost -= 0.04
    if profile.paid_only and any(w in blob.lower() for w in ("unpaid", "no pay", "stipend only", "volunteer")):
        return 0.0, ["Marked unpaid — you asked for paid only."]

    seniority = (profile.seniority or "mid").lower()
    low = blob.lower()
    if seniority in {"mid", "senior"} and any(w in low for w in INTERN_RE):
        loc_boost -= 0.16
    if seniority == "intern" and any(w in low for w in ("senior", "lead", "8+ years", "10+ years")):
        loc_boost -= 0.12

    recency = 0.0
    if opp.posted_at:
        age = utcnow() - to_utc(opp.posted_at)
        hours = age.total_seconds() / 3600
        if hours < 48:
            recency = 0.1
        elif hours < 168:
            recency = 0.04
        elif hours > 720:
            recency = -0.08

    verified = 0.08 if opp.verified_employer else 0.0
    skill_boost = min(0.22, 0.06 * len(skills))
    role_boost = 0.16 if roles else 0.0

    total = sim * 0.55 + skill_boost + role_boost + loc_boost + recency + verified
    total = max(0.0, min(0.99, total))

    if roles:
        reasons.insert(0, f"Close to your target role: {roles[0]}.")
    if skills:
        sample = ", ".join(skills[:3])
        reasons.append(f"Matches your {sample} skill{'s' if len(skills) != 1 else ''}.")
    if opp.source == "workdey":
        reasons.append("Listed on WorkDey — first-party, already in the house.")
    if not reasons and total >= 0.35:
        reasons.append("Related to the skills and roles on your profile.")

    return round(total, 3), reasons[:2]


def fingerprint(source: str, url: str, title: str, body: str) -> str:
    import hashlib

    key = f"{source}|{(url or '').split('?')[0].rstrip('/').lower()}|{(title or '')[:80].lower()}|{(body or '')[:180].lower()}"
    return hashlib.sha256(key.encode()).hexdigest()[:40]
