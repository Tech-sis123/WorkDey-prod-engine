"""Ingest → classify → store → match due watches.

Now powered by the workdey-career-agent-task actor.
"""

from __future__ import annotations

import logging
from datetime import timedelta
import dateutil.parser

from sqlalchemy.exc import IntegrityError

from config import Config
from workdey.adapters.apify import run_task
from workdey.db import db
from workdey.models import Heartbeat, Match, Opportunity, Draft, User, Watch
from workdey.timeutil import skip_quiet_hours, utcnow
from workdey.services.matcher import fingerprint
from workdey.services.notify import can_email, emails_today, send_digest, send_match_email

log = logging.getLogger("workdey.pipeline")


def beat(name: str, ok: bool = True, error: str = "", **detail):
    row = Heartbeat.query.get(name)
    if not row:
        row = Heartbeat(name=name)
        db.session.add(row)
    row.last_ok_at = utcnow()
    row.ok = ok
    row.last_error = error or ""
    row.detail = detail
    db.session.commit()


def upsert_opportunity(draft: dict) -> Opportunity | None:
    if not draft.get("fingerprint"):
        return None
    existing = Opportunity.query.filter_by(fingerprint=draft["fingerprint"]).one_or_none()
    if existing:
        return existing
    url = (draft.get("external_url") or "").split("?")[0].rstrip("/")
    if url:
        other = Opportunity.query.filter(Opportunity.external_url.startswith(url)).first()
        if other:
            return other
    row = Opportunity(**{k: v for k, v in draft.items() if k != "adapter" and hasattr(Opportunity, k)})
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return Opportunity.query.filter_by(fingerprint=draft["fingerprint"]).one_or_none()
    return row


def schedule_next(watch: Watch) -> None:
    nxt = utcnow() + timedelta(hours=max(1, watch.cadence_hours))
    watch.next_run_at = skip_quiet_hours(nxt, watch.quiet_start, watch.quiet_end, Config.TIMEZONE)


def run_user_actor(user: User) -> list[Match]:
    profile = user.profile
    watch = user.watch
    if not profile or not watch:
        return []
    if profile.completeness_score() < 40 and not Config.DEMO_MODE:
        return []

    token = Config.APIFY_API_TOKEN
    if not token:
        log.error("APIFY_API_TOKEN missing")
        return []

    input_data = {
        "fullName": user.name or user.email,
        "email": "", # We send the email ourselves
        "targetRoles": profile.target_roles or ["Software Engineer"],
        "preferredLocations": profile.locations or ["Remote"],
        "cvText": profile.cv_text or profile.summary or "Software Engineer",
        "minScore": int((watch.match_threshold or 0.42) * 100),
        "maxPacks": 1, # Actor schema requires >= 1. We just ignore it and generate on demand via Groq.
        "resetMemory": False
    }

    try:
        run_id, items = run_task(
            token, 
            Config.ACTORS["workdey_career"], 
            input_data, 
            wait_secs=600, 
            timeout=600
        )
    except Exception as exc:
        log.exception("apify run failed for user %s", user.email)
        return []

    created_matches = []
    
    for it in items:
        url = it.get("url") or ""
        title = it.get("title") or ""
        body = it.get("rawText") or it.get("description") or ""
        source = it.get("source", "workdey")
        fp = fingerprint(source, url, title, body)
        
        opp_data = {
            "source": source,
            "external_id": str(it.get("id") or url),
            "external_url": url,
            "author_name": it.get("company") or "",
            "title_guess": title[:240],
            "body": body[:8000],
            "location_guess": (it.get("location") or "")[:120],
            "lang": "en",
            "job_confidence": 1.0 if not it.get("isScam") else 0.0,
            "scam_risk": 1.0 if it.get("isScam") else 0.0,
            "classification": "job",
            "fingerprint": fp,
        }
        
        try:
            if it.get("postedAt"):
                opp_data["posted_at"] = dateutil.parser.isoparse(it.get("postedAt"))
            else:
                opp_data["posted_at"] = utcnow()
        except:
            opp_data["posted_at"] = utcnow()
            
        opp = upsert_opportunity(opp_data)
        if not opp:
            continue
            
        status = it.get("status")
        if status == "MATCHED":
            existing_match = Match.query.filter_by(user_id=user.id, opportunity_id=opp.id).first()
            if not existing_match:
                m = Match(
                    user_id=user.id,
                    opportunity_id=opp.id,
                    fit_score=(it.get("score") or 0) / 100.0,
                    fit_reasons=it.get("fitReasons") or [],
                    status="new",
                    emailed_at=None,
                )
                db.session.add(m)
                
                pack = it.get("applicationPack")
                if pack:
                    if pack.get("coverLetter"):
                        db.session.add(Draft(match=m, kind="cover_letter", body=pack["coverLetter"], facts_used=pack.get("factsUsed") or []))
                    if pack.get("reply"):
                        db.session.add(Draft(match=m, kind="recruiter_reply", body=pack["reply"]))
                
                created_matches.append(m)

    db.session.commit()
    return created_matches


def notify_user(user: User, matches: list[Match]) -> int:
    watch = user.watch
    if not matches or not watch:
        return 0
    fresh = [m for m in matches if m.emailed_at is None]
    if not fresh:
        return 0
    if not can_email(watch):
        return 0
    room = 99 if watch.alert_every_match else max(0, Config.EMAIL_DAILY_CAP - emails_today(watch))
    batch = fresh[: min(3, room)]
    if not batch:
        return 0
    if len(batch) == 1:
        send_match_email(user, batch[0])
    else:
        send_digest(user, batch)
    watch.emails_sent_count = emails_today(watch) + 1
    for m in batch:
        m.emailed_at = utcnow()
    return len(batch)


def run_due_watches(limit: int = 25) -> dict:
    now = utcnow()
    due = (
        Watch.query.filter(Watch.enabled.is_(True), Watch.next_run_at.isnot(None), Watch.next_run_at <= now)
        .limit(limit)
        .all()
    )
    ran = 0
    mailed = 0
    new_matches = 0
    for watch in due:
        if watch.paused_until and watch.paused_until > now:
            schedule_next(watch)
            continue
        user = db.session.get(User, watch.user_id)
        if not user:
            continue
            
        created = run_user_actor(user)
        mailed += notify_user(user, created)
        watch.last_run_at = now
        schedule_next(watch)
        ran += 1
        new_matches += len(created)
        
    db.session.commit()
    beat("matcher", True, ran=ran, matches=new_matches, mailed=mailed)
    return {"ran": ran, "matches": new_matches, "mailed": mailed}


def run_user_now(user: User) -> dict:
    created = run_user_actor(user)
    mailed = notify_user(user, created)
    if user.watch:
        user.watch.last_run_at = utcnow()
        schedule_next(user.watch)
    db.session.commit()
    return {"matches": len(created), "mailed": mailed, "ids": [m.id for m in created]}
