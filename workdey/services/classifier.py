"""Job / gig / not-a-job / scam classifier. Precision first — high-risk never emails."""

from __future__ import annotations

import re
from dataclasses import dataclass

JOB_HINTS = (
    r"\bhiring\b", r"\bwe'?re hiring\b", r"\bwe are hiring\b", r"\bvacancy\b",
    r"\bvacancies\b", r"\bjob opening\b", r"\bopen role\b", r"\bjoin (our|the) team\b",
    r"\bsend (your )?(cv|resume)\b", r"\bdm (your )?(cv|resume|portfolio)\b",
    r"\blooking for (a |an )?", r"\bnow hiring\b", r"\bto apply\b",
    r"\bapply (now|here|via|with)\b", r"\brole:\b", r"\bposition:\b",
    r"\bjob(s)? in (lagos|abuja|ph|nigeria)\b", r"\b#hiring", r"\b#jobsin",
    r"\bwe need (a |an )?", r"\bimmediate(ly)? (needed|hiring)\b",
    r"\bnysc\b", r"\bcorp member\b", r"\bfull[- ]?time\b", r"\bpart[- ]?time\b",
    r"\bcontract\b", r"\bremote[- ]?nigeria\b",
)
GIG_HINTS = (
    r"\bgig\b", r"\bva\b", r"\bvirtual assistant\b", r"\bdriver needed\b",
    r"\bartisan\b", r"\bfreelance\b", r"\bdm for pitch\b", r"\bneed a designer\b",
    r"\bneed a (va|driver|writer|dev|developer)\b", r"\bwho can\b",
    r"\bone[- ]off\b", r"\bthis week only\b",
)
SCAM_HINTS = (
    r"\bpay (before|to start|for (the )?interview)\b", r"\bregistration fee\b",
    r"\bagent fee\b", r"\bupfront (fee|payment)\b", r"\bsend money\b",
    r"\bgift card\b", r"\bwestern union\b", r"\bbitcoin\b", r"\busdt\b",
    r"\bwhatsapp me to pay\b", r"\bprocessing fee\b", r"\bvisa sponsorship fee\b",
    r"\bguaranteed job\b.{0,40}\bpay\b", r"\bwork from home.{0,30}\b\$\d{3,}",
    r"\bno experience.{0,20}\bearn\b", r"\bclick (this|the) link to receive\b",
)
NOT_JOB = (
    r"\bhiring manager\b", r"\bhired!\b", r"\bjust got hired\b",
    r"\bmy hiring process\b", r"\bhiring freeze\b", r"\bwe stopped hiring\b",
)

CITY_RE = re.compile(
    r"\b(lagos|ikeja|lekki|yaba|vi|victoria island|abuja|port harcourt|ph|"
    r"ibadan|kano|enugu|benin|kaduna|warri|owerri|onitsha|abeokuta|remote|"
    r"nigeria|cameroon|nairobi|accra|kenya|ghana)\b",
    re.I,
)
ROLE_RE = re.compile(
    r"\b((?:junior|senior|lead|mid[- ]level)?\s?(?:data analyst|product designer|"
    r"product manager|software engineer|frontend engineer|backend engineer|"
    r"full[- ]stack(?: engineer)?|accountant|virtual assistant|va|driver|"
    r"customer success|sales executive|hr officer|graphic designer|"
    r"content writer|social media manager|nurse|teacher|dev(?:eloper)?))\b",
    re.I,
)


@dataclass
class ClassResult:
    classification: str
    job_confidence: float
    scam_risk: float
    title_guess: str
    location_guess: str
    employment_type_guess: str


def _hits(patterns: tuple[str, ...], text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.I))


def classify(title: str, body: str, source: str = "") -> ClassResult:
    blob = f"{title}\n{body}".strip()
    low = blob.lower()
    job_n = _hits(JOB_HINTS, low)
    gig_n = _hits(GIG_HINTS, low)
    scam_n = _hits(SCAM_HINTS, low)
    not_n = _hits(NOT_JOB, low)

    scam_risk = min(1.0, 0.22 * scam_n + (0.35 if "fee" in low and "apply" in low else 0))
    if scam_n >= 2:
        scam_risk = max(scam_risk, 0.75)

    if not_n and job_n <= 1:
        classification = "not_a_job"
        conf = 0.15
    elif scam_risk >= 0.6:
        classification = "likely_scam"
        conf = 0.2
    elif gig_n and job_n <= 1:
        classification = "gig"
        conf = min(0.92, 0.45 + 0.12 * gig_n + 0.08 * job_n)
    elif job_n or source == "workdey" or source == "linkedin":
        classification = "job"
        conf = min(0.97, 0.38 + 0.12 * job_n + (0.25 if source in {"workdey", "linkedin"} else 0))
    else:
        classification = "not_a_job"
        conf = 0.12

    role = ROLE_RE.search(blob)
    title_guess = (role.group(1).strip().title() if role else (title or body[:80])).strip()[:180]
    loc = CITY_RE.search(blob)
    location_guess = loc.group(1).title() if loc else ""
    if re.search(r"\bremote\b", low):
        location_guess = location_guess or "Remote"
    emp = "gig" if classification == "gig" else "full-time"
    if re.search(r"\b(contract|part[- ]?time)\b", low):
        emp = "contract"
    if re.search(r"\bremote\b", low):
        emp = emp
    return ClassResult(classification, round(conf, 3), round(scam_risk, 3), title_guess, location_guess, emp)
