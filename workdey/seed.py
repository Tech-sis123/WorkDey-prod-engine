"""First-party WorkDey jobs + a demo seeker so the inbox is never empty."""

from __future__ import annotations

from datetime import timedelta

from werkzeug.security import generate_password_hash

from config import Config
from workdey.db import db
from workdey.models import Match, Opportunity, Profile, Setting, User, Watch
from workdey.services.classifier import classify
from workdey.services.matcher import fingerprint, score
from workdey.timeutil import utcnow

JOBS = [
    {
        "title": "Junior Data Analyst",
        "company": "Flutterwave",
        "location": "Lagos",
        "type": "full-time",
        "body": (
            "We are hiring a Junior Data Analyst in Lagos. Excel, SQL, and a calm head for messy "
            "spreadsheets. BSc or HND. NYSC completed or exempting is a plus. Apply with CV."
        ),
        "url": "https://workdey.app/jobs/junior-data-analyst-lagos",
        "verified": True,
    },
    {
        "title": "Product Designer",
        "company": "Paystack",
        "location": "Remote-Nigeria",
        "type": "full-time",
        "body": (
            "Product Designer, remote-Nigeria. Figma, user research, and shipped mobile flows. "
            "Join our team. Full-time. Send portfolio + CV."
        ),
        "url": "https://workdey.app/jobs/product-designer-remote",
        "verified": True,
    },
    {
        "title": "Virtual Assistant (gig)",
        "company": "Aunty B Ventures",
        "location": "Lagos",
        "type": "gig",
        "body": (
            "Need a VA this month. Calendar, customer WhatsApp, light bookkeeping in Excel. "
            "DM for pitch. Paid weekly. Lagos or remote."
        ),
        "url": "https://x.com/auntyb/status/demo-va",
        "source": "x",
        "verified": False,
    },
    {
        "title": "Accountant",
        "company": "Farmcrowdy",
        "location": "Abuja",
        "type": "full-time",
        "body": (
            "Accountant, Abuja. ICAN in view, Excel, QuickBooks, bookkeeping. We are hiring. "
            "HND/BSc Accounting. Send CV."
        ),
        "url": "https://www.linkedin.com/jobs/view/demo-accountant",
        "source": "linkedin",
        "verified": True,
    },
    {
        "title": "Frontend Engineer",
        "company": "PiggyVest",
        "location": "Lagos",
        "type": "full-time",
        "body": (
            "Frontend Engineer, Lagos. React, TypeScript, accessibility. We're hiring. "
            "2+ years. Apply now with CV and GitHub."
        ),
        "url": "https://workdey.app/jobs/frontend-engineer-lagos",
        "verified": True,
    },
    {
        "title": "Dispatch rider / driver",
        "company": "Keke Logistics",
        "location": "Ikeja",
        "type": "gig",
        "body": (
            "Driver needed in Ikeja this week. Okada or car. Valid papers. Daily pay. "
            "WhatsApp to apply. Gig, not full-time."
        ),
        "url": "https://www.instagram.com/p/demo-driver/",
        "source": "instagram",
        "verified": False,
    },
    {
        "title": "Customer Success Associate",
        "company": "Mono",
        "location": "Lagos",
        "type": "full-time",
        "body": (
            "Customer Success Associate. Lagos / hybrid. Calm written English, CRM, follow-ups. "
            "Open role, full-time. NYSC done. Send CV."
        ),
        "url": "https://workdey.app/jobs/cs-associate",
        "verified": True,
    },
    {
        "title": "Pay before interview — data clerk",
        "company": "Global Placement Ltd",
        "location": "Lagos",
        "type": "full-time",
        "body": (
            "Guaranteed job. Pay a registration fee of ₦45,000 before the interview. "
            "Send money to our agent on WhatsApp. Work from home, earn $5000."
        ),
        "url": "https://example.invalid/scam",
        "source": "x",
        "verified": False,
    },
]


def ensure_first_party_jobs() -> int:
    n = 0
    now = utcnow()
    for i, job in enumerate(JOBS):
        source = job.get("source", "workdey")
        fp = fingerprint(source, job["url"], job["title"], job["body"])
        if Opportunity.query.filter_by(fingerprint=fp).first():
            continue
        c = classify(job["title"], job["body"], source)
        row = Opportunity(
            source=source,
            external_id=job["url"],
            external_url=job["url"],
            author_handle=job["company"].replace(" ", "").lower(),
            author_name=job["company"],
            title_guess=job["title"],
            body=job["body"],
            location_guess=job["location"],
            employment_type_guess=job["type"],
            posted_at=now - timedelta(hours=4 + i * 3),
            job_confidence=c.job_confidence,
            scam_risk=c.scam_risk,
            classification=c.classification,
            fingerprint=fp,
            verified_employer=job.get("verified", False),
            raw_snapshot={"seed": True},
        )
        db.session.add(row)
        n += 1
    db.session.commit()
    return n


def _demo_user() -> User:
    u = User.query.filter_by(email=Config.DEMO_EMAIL).one_or_none()
    if u:
        return u
    u = User(
        email=Config.DEMO_EMAIL,
        password_hash=generate_password_hash(Config.DEMO_PASSWORD),
        name="Esabu Blessing",
        is_admin=True,
    )
    db.session.add(u)
    db.session.flush()
    p = Profile(
        user_id=u.id,
        skills_text="Excel, SQL, bookkeeping, customer WhatsApp, Figma basics",
        skills_tags=["Excel", "SQL", "bookkeeping", "customer service", "Figma"],
        education="BSc Accounting, University of Lagos · NYSC completed",
        years_experience=3,
        target_roles=["Data Analyst", "Accountant", "Virtual Assistant"],
        locations=["Lagos", "Remote"],
        work_type="either",
        paid_only=True,
        seniority="mid",
        summary="Lagos-based operator who keeps numbers clean and customers answered.",
        cv_text=(
            "Esabu Blessing\nData Analyst / Accountant\nLagos\n"
            "BSc Accounting, UNILAG. NYSC completed 2023.\n"
            "Excel, SQL, QuickBooks, bookkeeping, customer WhatsApp.\n"
            "3 years: finance ops at a Lagos SME, reporting, collections."
        ),
    )
    p.completeness_score()
    db.session.add(p)
    w = Watch(
        user_id=u.id,
        enabled=True,
        cadence_hours=24,
        email_on=True,
        last_run_at=utcnow() - timedelta(hours=20),
        next_run_at=utcnow(),
        sources={"x": True, "linkedin": True, "instagram": True, "workdey": True},
    )
    db.session.add(w)
    db.session.commit()
    return u


def seed_demo_matches(user: User) -> None:
    if Match.query.filter_by(user_id=user.id).count():
        return
    profile = user.profile
    opps = Opportunity.query.filter(Opportunity.killed.is_(False)).all()
    for opp in opps:
        s, reasons = score(profile, opp)
        if s < 0.35 and opp.classification != "likely_scam":
            continue
        if opp.classification == "likely_scam":
            continue
        db.session.add(
            Match(
                user_id=user.id,
                opportunity_id=opp.id,
                fit_score=s,
                fit_reasons=reasons or ["Related to your Excel + bookkeeping skills; Lagos."],
                status="new",
            )
        )
    db.session.commit()


def seed_if_needed() -> None:
    if not Setting.query.get("seeded"):
        db.session.add(Setting(key="seeded", value="1"))
        for src, on in Config.SOURCE_FLAGS.items():
            db.session.merge(Setting(key=f"kill.{src}", value="0" if on else "1"))
        db.session.commit()
    ensure_first_party_jobs()
    if Config.DEMO_MODE:
        u = _demo_user()
        seed_demo_matches(u)
