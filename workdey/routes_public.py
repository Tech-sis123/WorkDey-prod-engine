from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, session

from config import Config
from workdey.db import db
from workdey.models import MagicToken, Match, User, Watch
from workdey.pipeline import schedule_next
from workdey.timeutil import utcnow

public_bp = Blueprint("public", __name__)


@public_bp.get("/")
def index():
    return render_template("index.html", app_name="WorkDey")


@public_bp.get("/app")
@public_bp.get("/app/")
def app_page():
    return render_template("index.html", app_name="WorkDey")


@public_bp.get("/health")
@public_bp.get("/ping")
def ping():
    return jsonify(
        {
            "ok": True,
            "service": "workdey-engine",
            "time": utcnow().isoformat(),
            "apify": bool(Config.APIFY_API_TOKEN),
            "brevo": bool(Config.BREVO_API_KEY),
        }
    )


@public_bp.get("/i/<token>")
def inbox_link(token):
    u = User.query.filter_by(unsub_token=token).one_or_none()
    if not u:
        return redirect("/app#inbox")
    session["uid"] = u.id
    dest = "/app#inbox"
    # preserve a hash if the welcome mail pointed at profile
    frag = (request.args.get("next") or "").strip()
    if frag in {"profile", "watch", "inbox"}:
        dest = f"/app#{frag}"
    return redirect(dest)


@public_bp.get("/m/<token>")
def deep_link(token):
    m = Match.query.filter_by(deep_link_token=token).one_or_none()
    if not m:
        return redirect("/app#inbox")
    session["uid"] = m.user_id
    session["continue_match"] = m.id
    return redirect(f"/app#match/{m.id}")


@public_bp.get("/auth/magic/<token>")
def magic(token):
    row = db.session.get(MagicToken, token)
    if not row or row.used or row.expires_at < utcnow():
        return redirect("/?magic=expired")
    row.used = True
    session["uid"] = row.user_id
    if row.match_id:
        return redirect(f"/app#match/{row.match_id}")
    db.session.commit()
    return redirect("/app")


@public_bp.get("/unsub/<token>")
def unsub(token):
    u = User.query.filter_by(unsub_token=token).one_or_none()
    if u and u.watch:
        u.watch.email_on = False
        db.session.commit()
    return render_template("simple.html", title="Unsubscribed", body="You will not get Watch emails from WorkDey. You can turn them back on in Watch settings.")


@public_bp.get("/pause/<token>")
def pause(token):
    u = User.query.filter_by(unsub_token=token).one_or_none()
    if u and u.watch:
        u.watch.paused_until = utcnow() + timedelta(days=7)
        schedule_next(u.watch)
        db.session.commit()
    return render_template("simple.html", title="Watch paused", body="WorkDey will not hunt for you for 7 days. Open the app to resume.")


@public_bp.get("/download/engine.zip")
def download_zip():
    from pathlib import Path

    from flask import send_file

    candidates = [
        Path("/workspace/artifacts/WorkDey_Smart_Match_Engine.zip"),
        Path("/workspace/workdey_engine/WorkDey_Smart_Match_Engine.zip"),
        Config.ROOT / "WorkDey_Smart_Match_Engine.zip",
    ]
    for z in candidates:
        if z.exists():
            return send_file(z, as_attachment=True, download_name="WorkDey_Smart_Match_Engine.zip")
    return jsonify({"error": "zip not built yet"}), 404
