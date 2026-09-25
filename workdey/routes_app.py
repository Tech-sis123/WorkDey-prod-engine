from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import desc

from config import Config
from workdey.db import db
from workdey.models import Draft, Match, Opportunity, Profile, Report, Watch
from workdey.pipeline import run_user_now, schedule_next
from workdey.routes_auth import current_user, login_required
from workdey.services import cv as cvsvc
from workdey.services import llm as llmsvc
from workdey.services.pdf import render_letter
from workdey.timeutil import iso, utcnow

app_bp = Blueprint("appapi", __name__)


def _profile_json(p: Profile | None) -> dict:
    if not p:
        return {}
    return {
        "skills_text": p.skills_text,
        "skills_tags": p.skills_tags or [],
        "education": p.education,
        "years_experience": p.years_experience,
        "target_roles": p.target_roles or [],
        "locations": p.locations or [],
        "work_type": p.work_type,
        "paid_only": p.paid_only,
        "seniority": p.seniority,
        "summary": p.summary,
        "linkedin_url": p.linkedin_url,
        "x_handle": p.x_handle,
        "has_cv": bool(p.cv_text),
        "completeness": p.completeness,
    }


def _watch_json(w: Watch | None) -> dict:
    if not w:
        return {}
    return {
        "enabled": w.enabled,
        "cadence_hours": w.cadence_hours,
        "quiet_start": w.quiet_start,
        "quiet_end": w.quiet_end,
        "email_on": w.email_on,
        "alert_every_match": w.alert_every_match,
        "sources": w.sources or {},
        "paused_until": iso(w.paused_until),
        "last_run_at": iso(w.last_run_at),
        "next_run_at": iso(w.next_run_at),
        "emails_sent_count": w.emails_sent_count,
        "match_threshold": w.match_threshold,
    }


def _opp_json(o: Opportunity) -> dict:
    return {
        "id": o.id,
        "source": o.source,
        "external_url": o.external_url,
        "author_handle": o.author_handle,
        "author_name": o.author_name,
        "title": o.title_guess,
        "body": o.body,
        "location": o.location_guess,
        "employment_type": o.employment_type_guess,
        "posted_at": iso(o.posted_at),
        "job_confidence": o.job_confidence,
        "scam_risk": o.scam_risk,
        "classification": o.classification,
        "verified": o.verified_employer,
    }


def _match_json(m: Match, full: bool = False) -> dict:
    o = m.opportunity
    pack = "formal" if o.source == "linkedin" else "informal"
    d = {
        "id": m.id,
        "status": m.status,
        "fit_score": m.fit_score,
        "fit_reasons": m.fit_reasons or [],
        "created_at": iso(m.created_at),
        "pack": pack,
        "deep_link": f"/m/{m.deep_link_token}",
        "opportunity": _opp_json(o) if full else {
            "id": o.id,
            "source": o.source,
            "title": o.title_guess,
            "author_name": o.author_name,
            "location": o.location_guess,
            "classification": o.classification,
            "posted_at": iso(o.posted_at),
        },
    }
    if full:
        d["drafts"] = [
            {"id": x.id, "kind": x.kind, "body": x.body, "facts_used": x.facts_used, "created_at": iso(x.created_at)}
            for x in sorted(m.drafts, key=lambda x: x.created_at, reverse=True)[:9]
        ]
    return d


@app_bp.before_request
def _gate():
    if request.method == "OPTIONS":
        return
    u = current_user()
    if not u:
        return jsonify({"error": "auth_required"}), 401
    g.user = u


@app_bp.get("/state")
def state():
    u = g.user
    unread = Match.query.filter_by(user_id=u.id, status="new").count()
    return jsonify(
        {
            "user": {"id": u.id, "email": u.email, "name": u.name, "demo": u.email == Config.DEMO_EMAIL},
            "profile": _profile_json(u.profile),
            "watch": _watch_json(u.watch),
            "unread": unread,
            "keys": {
                "apify": bool(Config.APIFY_API_TOKEN),
                "brevo": bool(Config.BREVO_API_KEY),
                "groq": bool(Config.GROQ_API_KEY),
            },
        }
    )


@app_bp.post("/profile")
def save_profile():
    p = g.user.profile
    if not p:
        p = Profile(user_id=g.user.id)
        db.session.add(p)
    data = request.get_json(force=True, silent=True) or {}
    for field in (
        "skills_text",
        "education",
        "summary",
        "linkedin_url",
        "x_handle",
        "work_type",
        "seniority",
    ):
        if field in data and data[field] is not None:
            setattr(p, field, str(data[field])[:4000])
    if "skills_tags" in data and isinstance(data["skills_tags"], list):
        p.skills_tags = [str(x)[:40] for x in data["skills_tags"][:24]]
    if "target_roles" in data and isinstance(data["target_roles"], list):
        p.target_roles = [str(x)[:80] for x in data["target_roles"][:3]]
    if "locations" in data and isinstance(data["locations"], list):
        p.locations = [str(x)[:80] for x in data["locations"][:6]]
    if "years_experience" in data:
        try:
            p.years_experience = max(0, min(40, int(data["years_experience"])))
        except (TypeError, ValueError):
            pass
    if "paid_only" in data:
        p.paid_only = bool(data["paid_only"])
    if "name" in data and data["name"]:
        g.user.name = str(data["name"])[:120]
    p.completeness_score()
    db.session.commit()
    return jsonify({"profile": _profile_json(p)})


@app_bp.post("/profile/cv")
def upload_cv():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "attach a PDF or DOCX"}), 400
    data = f.read()
    text = cvsvc.extract_text(f.filename, data)
    path = cvsvc.save_upload(Config.UPLOAD_DIR, g.user.id, f.filename, data)
    p = g.user.profile
    p.cv_path = str(path)
    p.cv_text = text[:20000]
    drafted = cvsvc.draft_fields(text)
    if drafted.get("skills_tags") and not p.skills_tags:
        p.skills_tags = drafted["skills_tags"]
    if drafted.get("education") and not p.education:
        p.education = drafted["education"]
    if drafted.get("years_experience") and not p.years_experience:
        p.years_experience = drafted["years_experience"]
    p.completeness_score()
    db.session.commit()
    return jsonify({"profile": _profile_json(p), "extracted": drafted, "chars": len(text)})


@app_bp.post("/watch")
def save_watch():
    w = g.user.watch
    if not w:
        w = Watch(user_id=g.user.id)
        db.session.add(w)
    data = request.get_json(force=True, silent=True) or {}
    if "enabled" in data:
        w.enabled = bool(data["enabled"])
    if "cadence_hours" in data:
        c = int(data["cadence_hours"])
        if c not in {1, 3, 6, 12, 24}:
            return jsonify({"error": "cadence must be 1, 3, 6, 12 or 24 hours"}), 400
        w.cadence_hours = c
    if "quiet_start" in data:
        w.quiet_start = str(data["quiet_start"])[:8]
    if "quiet_end" in data:
        w.quiet_end = str(data["quiet_end"])[:8]
    if "email_on" in data:
        w.email_on = bool(data["email_on"])
    if "alert_every_match" in data:
        w.alert_every_match = bool(data["alert_every_match"])
    if "sources" in data and isinstance(data["sources"], dict):
        w.sources = {k: bool(v) for k, v in data["sources"].items() if k in {"x", "linkedin", "instagram", "workdey"}}
    if "match_threshold" in data:
        try:
            w.match_threshold = max(0.2, min(0.85, float(data["match_threshold"])))
        except (TypeError, ValueError):
            pass
    if w.enabled:
        if not w.next_run_at or w.next_run_at < utcnow():
            w.next_run_at = utcnow()
            schedule_next(w)
    else:
        w.next_run_at = None
    db.session.commit()
    return jsonify({"watch": _watch_json(w)})


@app_bp.post("/watch/run")
def run_now():
    result = run_user_now(g.user)
    return jsonify(result)


@app_bp.get("/matches")
def list_matches():
    status = request.args.get("status")
    q = Match.query.filter_by(user_id=g.user.id)
    if status:
        q = q.filter_by(status=status)
    rows = q.order_by(desc(Match.created_at)).limit(80).all()
    return jsonify({"matches": [_match_json(m) for m in rows]})


@app_bp.get("/matches/<mid>")
def get_match(mid):
    m = Match.query.filter_by(id=mid, user_id=g.user.id).one_or_none()
    if not m:
        return jsonify({"error": "not found"}), 404
    if m.status == "new":
        m.status = "viewed"
        m.viewed_at = utcnow()
        db.session.commit()
    return jsonify({"match": _match_json(m, full=True)})


@app_bp.post("/matches/<mid>/status")
def set_status(mid):
    m = Match.query.filter_by(id=mid, user_id=g.user.id).one_or_none()
    if not m:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    st = data.get("status")
    if st not in {"viewed", "drafting", "applied", "dismissed", "spam", "new"}:
        return jsonify({"error": "bad status"}), 400
    m.status = st
    if st in {"spam", "dismissed"}:
        reason = "scam" if st == "spam" else data.get("reason") or "not_a_job"
        db.session.add(
            Report(user_id=g.user.id, match_id=m.id, opportunity_id=m.opportunity_id, reason=reason)
        )
        if st == "spam":
            m.opportunity.scam_risk = max(m.opportunity.scam_risk, 0.7)
    db.session.commit()
    return jsonify({"match": _match_json(m)})


@app_bp.post("/matches/<mid>/generate")
def generate(mid):
    m = Match.query.filter_by(id=mid, user_id=g.user.id).one_or_none()
    if not m:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    kind = data.get("kind") or "reply"
    if kind not in {"reply", "cover", "cv"}:
        return jsonify({"error": "kind must be reply, cover, or cv"}), 400
    today = utcnow().date().isoformat()
    n = Draft.query.filter(Draft.match_id == m.id, Draft.created_at >= utcnow().replace(hour=0, minute=0)).count()
    # cheap per-user cap across all matches today
    from sqlalchemy import func
    from workdey.models import Draft as D

    used = (
        db.session.query(func.count(D.id))
        .join(Match, Match.id == D.match_id)
        .filter(Match.user_id == g.user.id, D.created_at >= utcnow() - timedelta(hours=24))
        .scalar()
        or 0
    )
    if used >= Config.LLM_DAILY_CAP:
        return jsonify({"error": "daily AI cap reached — try again tomorrow"}), 429
    out = llmsvc.generate(g.user.profile, m, kind, str(data.get("note") or "")[:240])
    row = Draft(match_id=m.id, kind=kind, body=out["body"], facts_used=out.get("facts_used") or [], note=str(data.get("note") or "")[:240])
    db.session.add(row)
    m.status = "drafting"
    db.session.commit()
    return jsonify(
        {
            "draft": {"id": row.id, "kind": kind, "body": row.body, "facts_used": row.facts_used, "fallback": out.get("fallback"), "refused": out.get("refused")},
        }
    )


@app_bp.get("/matches/<mid>/pdf/<kind>")
def pdf(mid, kind):
    m = Match.query.filter_by(id=mid, user_id=g.user.id).one_or_none()
    if not m:
        return jsonify({"error": "not found"}), 404
    if kind not in {"cover", "cv", "reply"}:
        return jsonify({"error": "bad kind"}), 400
    d = next((x for x in sorted(m.drafts, key=lambda x: x.created_at, reverse=True) if x.kind == kind), None)
    if not d:
        return jsonify({"error": "generate a draft first"}), 404
    title = {"cover": "Cover letter", "cv": "CV revamp", "reply": "Reply"}[kind] + f" — {m.opportunity.title_guess}"
    blob = render_letter(title, d.body)
    return Response(
        blob,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="workdey-{kind}-{m.id}.pdf"'},
    )
