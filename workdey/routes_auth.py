from __future__ import annotations

import secrets
from datetime import timedelta
from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from workdey.db import db
from workdey.models import MagicToken, Profile, User, Watch
from workdey.pipeline import schedule_next
from workdey.timeutil import utcnow

auth_bp = Blueprint("auth", __name__)


def current_user() -> User | None:
    uid = session.get("uid")
    if not uid:
        return None
    return db.session.get(User, uid)


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "auth_required"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapped


def public_user(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "name": u.name,
        "is_admin": u.is_admin,
        "demo": u.email == Config.DEMO_EMAIL,
    }


@auth_bp.post("/signup")
def signup():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    if not email or "@" not in email or len(password) < 8:
        return jsonify({"error": "email and a password of 8+ characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "that email already has an account"}), 409
    u = User(email=email, password_hash=generate_password_hash(password), name=name or email.split("@")[0])
    db.session.add(u)
    db.session.flush()
    db.session.add(Profile(user_id=u.id))
    w = Watch(user_id=u.id, enabled=False, cadence_hours=24, next_run_at=None)
    db.session.add(w)
    db.session.commit()
    session["uid"] = u.id
    welcome = "skipped"
    try:
        from workdey.services.mailer import send_welcome

        row = send_welcome(u)
        db.session.commit()
        welcome = row.status
    except Exception:
        db.session.rollback()
        session["uid"] = u.id
        welcome = "failed"
    return jsonify({"user": public_user(u), "welcome_email": welcome})



@auth_bp.post("/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    u = User.query.filter_by(email=email).one_or_none()
    if not u or not check_password_hash(u.password_hash, password):
        return jsonify({"error": "wrong email or password"}), 401
    session["uid"] = u.id
    return jsonify({"user": public_user(u)})


@auth_bp.post("/demo")
def demo():
    u = User.query.filter_by(email=Config.DEMO_EMAIL).one_or_none()
    if not u:
        return jsonify({"error": "demo user missing"}), 404
    session["uid"] = u.id
    return jsonify({"user": public_user(u)})


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.get("/me")
def me():
    u = current_user()
    if not u:
        return jsonify({"user": None})
    return jsonify({"user": public_user(u)})


@auth_bp.post("/magic")
def request_magic():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    u = User.query.filter_by(email=email).one_or_none()
    if not u:
        return jsonify({"ok": True})  # do not leak
    tok = secrets.token_urlsafe(24)
    db.session.add(
        MagicToken(
            token=tok,
            user_id=u.id,
            purpose="login",
            expires_at=utcnow() + timedelta(hours=2),
        )
    )
    db.session.commit()
    link = f"{Config.APP_BASE_URL}/auth/magic/{tok}"
    # reuse outbox so Brevo still sends if configured
    from workdey.models import EmailOutbox

    db.session.add(
        EmailOutbox(
            user_id=u.id,
            to_email=u.email,
            subject="Your WorkDey login link",
            text=f"Open {link} — expires in 2 hours.",
            html=f'<p>Open <a href="{link}">{link}</a></p>',
            status="queued" if not Config.BREVO_API_KEY else "queued",
        )
    )
    db.session.commit()
    if Config.BREVO_API_KEY:
        try:
            import requests

            requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": Config.BREVO_API_KEY, "content-type": "application/json"},
                json={
                    "sender": {"name": Config.BREVO_SENDER_NAME, "email": Config.BREVO_SENDER_EMAIL},
                    "to": [{"email": u.email}],
                    "subject": "Your WorkDey login link",
                    "htmlContent": f'<p>Open <a href="{link}">this link</a> to sign in. Expires in 2 hours.</p>',
                },
                timeout=20,
            )
        except Exception:
            pass
    payload = {"ok": True}
    if Config.DEMO_MODE:
        payload["dev_link"] = link
    return jsonify(payload)
