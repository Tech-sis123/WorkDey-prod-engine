from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from config import Config
from workdey.db import db
from workdey.models import EmailOutbox, Heartbeat, Setting, SourceRun
from workdey.pipeline import run_due_watches, run_user_now
from workdey.routes_auth import current_user
from workdey.timeutil import iso
from workdey.workers import scheduler_status, start_background

ops_bp = Blueprint("ops", __name__)


@ops_bp.before_request
def _gate():
    if request.method == "OPTIONS":
        return
    u = current_user()
    if not u:
        return jsonify({"error": "auth_required"}), 401
    g.user = u


@ops_bp.get("/health")
def health():
    beats = {b.name: {"ok": b.ok, "at": iso(b.last_ok_at), "error": b.last_error, "detail": b.detail} for b in Heartbeat.query.all()}
    runs = (
        SourceRun.query.order_by(SourceRun.started_at.desc()).limit(12).all()
    )
    kills = {s.key.replace("kill.", ""): s.value for s in Setting.query.filter(Setting.key.startswith("kill.")).all()}
    return jsonify(
        {
            "scheduler": scheduler_status(),
            "heartbeats": beats,
            "kills": kills,
            "keys": {
                "apify": bool(Config.APIFY_API_TOKEN),
                "brevo": bool(Config.BREVO_API_KEY),
                "xai": bool(Config.XAI_API_KEY),
            },
            "runs": [
                {
                    "id": r.id,
                    "source": r.source,
                    "status": r.status,
                    "in": r.items_in,
                    "kept": r.items_kept,
                    "error": r.error,
                    "started_at": iso(r.started_at),
                    "apify_run_id": r.apify_run_id,
                }
                for r in runs
            ],
        }
    )


@ops_bp.post("/ingest")
def ingest():
    return jsonify({"error": "Global ingest is deprecated; jobs are now fetched per user."}), 400


@ops_bp.post("/match")
def match():
    if request.args.get("all") == "1" and g.user.is_admin:
        return jsonify(run_due_watches(limit=100))
    return jsonify(run_user_now(g.user))


@ops_bp.post("/kill")
def kill():
    data = request.get_json(force=True, silent=True) or {}
    source = data.get("source")
    on = bool(data.get("killed"))
    if source not in {"x", "linkedin", "linkedin_posts", "instagram", "workdey"}:
        return jsonify({"error": "unknown source"}), 400
    db.session.merge(Setting(key=f"kill.{source}", value="1" if on else "0"))
    db.session.commit()
    return jsonify({"source": source, "killed": on})


@ops_bp.get("/outbox")
def outbox():
    rows = EmailOutbox.query.filter_by(user_id=g.user.id).order_by(EmailOutbox.created_at.desc()).limit(30).all()
    return jsonify(
        {
            "emails": [
                {
                    "id": r.id,
                    "to": r.to_email,
                    "subject": r.subject,
                    "status": r.status,
                    "error": r.error,
                    "created_at": iso(r.created_at),
                    "html": r.html if r.status != "sent" else None,
                    "text": r.text,
                }
                for r in rows
            ]
        }
    )
