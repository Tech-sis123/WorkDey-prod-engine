"""Brevo mail, always from WorkDey, always signed off 'WorkDey for you!!!'."""

from __future__ import annotations

import html
import logging

import requests

from config import Config
from workdey.db import db
from workdey.models import EmailOutbox, User

log = logging.getLogger("workdey.mail")
BREVO = "https://api.brevo.com/v3/smtp/email"
SIGN_OFF = "WorkDey for you!!!"


def first_name(user: User) -> str:
    return (user.name or "there").split()[0] or "there"


def inbox_url(user: User) -> str:
    return f"{Config.APP_BASE_URL}/i/{user.unsub_token}"


def profile_url(user: User) -> str:
    return f"{Config.APP_BASE_URL}/i/{user.unsub_token}?next=profile"


def match_url(token: str) -> str:
    return f"{Config.APP_BASE_URL}/m/{token}"


def _wrap(*, name: str, body_html: str, body_text: str, buttons: list[tuple[str, str]], user: User) -> tuple[str, str]:
    parts: list[str] = []
    for i, (label, href) in enumerate(buttons):
        bg, fg = ("#d7ddd4", "#141714") if i == 0 else ("#1b1e1b", "#e8ebe4")
        parts.append(
            f'<a href="{html.escape(href)}" style="display:inline-block;margin:0 8px 8px 0;background:{bg};color:{fg};'
            f'text-decoration:none;padding:12px 18px;border-radius:999px;font-size:14px;font-weight:600;">'
            f"{html.escape(label)}</a>"
        )
    btns = "".join(parts)
    pause = f"{Config.APP_BASE_URL}/pause/{user.unsub_token}"
    unsub = f"{Config.APP_BASE_URL}/unsub/{user.unsub_token}"
    html_body = f"""<!doctype html>
<html><body style="margin:0;padding:24px;background:#0c0e0c;color:#e8ebe4;font-family:Georgia,'Times New Roman',serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:540px;margin:0 auto;background:#141714;border:1px solid #2a2e2a;border-radius:16px;">
    <tr><td style="padding:28px 28px 4px;font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#9aa394;">WorkDey</td></tr>
    <tr><td style="padding:12px 28px 0;font-size:17px;line-height:1.55;">Hey there, {html.escape(name)}.</td></tr>
    <tr><td style="padding:12px 28px 0;font-size:16px;line-height:1.6;color:#c6cdc0;">{body_html}</td></tr>
    <tr><td style="padding:22px 28px 4px;">{btns}</td></tr>
    <tr><td style="padding:18px 28px 10px;font-size:16px;font-weight:600;color:#e8ebe4;">{html.escape(SIGN_OFF)}</td></tr>
    <tr><td style="padding:0 28px 28px;font-size:12px;color:#7c8478;">
      Pause 7 days: <a href="{html.escape(pause)}" style="color:#c6cdc0;">pause</a>
      · Stop these emails: <a href="{html.escape(unsub)}" style="color:#c6cdc0;">unsubscribe</a>
    </td></tr>
  </table>
</body></html>"""
    text_btns = "\n".join(f"{label}: {href}" for label, href in buttons)
    text = (
        f"Hey there, {name}.\n\n{body_text.strip()}\n\n{text_btns}\n\n{SIGN_OFF}\n"
        f"Pause 7 days: {pause}\nUnsubscribe: {unsub}\n"
    )
    return html_body, text




def send(*, user: User, subject: str, html_body: str, text: str, match_id: str | None = None, tag: str = "workdey") -> EmailOutbox:
    row = EmailOutbox(
        user_id=user.id,
        match_id=match_id,
        to_email=user.email,
        subject=subject[:50],
        html=html_body,
        text=text,
        status="queued",
    )
    db.session.add(row)
    db.session.flush()
    if not Config.BREVO_API_KEY:
        row.status = "skipped"
        row.error = "BREVO_API_KEY missing — stored in outbox"
        return row
    try:
        res = requests.post(
            BREVO,
            headers={
                "api-key": Config.BREVO_API_KEY,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json={
                "sender": {"name": "WorkDey", "email": Config.BREVO_SENDER_EMAIL},
                "to": [{"email": user.email, "name": user.name or user.email}],
                "subject": subject[:50],
                "htmlContent": html_body,
                "textContent": text,
                "tags": [tag],
            },
            timeout=30,
        )
        if res.status_code >= 400:
            row.status = "failed"
            row.error = res.text[:400]
        else:
            row.status = "sent"
            row.provider_id = str((res.json() or {}).get("messageId") or "")
    except Exception as exc:
        row.status = "failed"
        row.error = str(exc)[:400]
        log.exception("brevo send failed")
    return row


def send_welcome(user: User) -> EmailOutbox:
    name = first_name(user)
    inbox = inbox_url(user)
    profile = profile_url(user)
    body_html = """
      <p>Welcome to WorkDey. From now on, every notification we send you will come from this same name — <strong>WorkDey</strong>.</p>
      <p>When we find a role that actually fits your skills, we email you a short note. From that mail you can open the original post, or jump into your inbox on the web app. Anything we have already scraped will be waiting there so you can ask Grok for a reply, a cover letter, or a CV tailored to the role.</p>
      <p>Fill in your profile, then turn Watch on. We stay quiet until then.</p>
    """
    body_text = (
        "Welcome to WorkDey. From now on, every notification we send you will come from this same name — WorkDey.\n\n"
        "When we find a role that actually fits your skills, we email you a short note. From that mail you can open "
        "the original post, or jump into your inbox on the web app. Anything we have already scraped will be waiting "
        "there so you can ask Grok for a reply, a cover letter, or a CV tailored to the role.\n\n"
        "Fill in your profile, then turn Watch on. We stay quiet until then."
    )
    html_body, text = _wrap(
        name=name,
        body_html=body_html,
        body_text=body_text,
        buttons=[("Open your inbox", inbox), ("Complete your profile", profile)],
        user=user,
    )
    return send(user=user, subject="Welcome to WorkDey", html_body=html_body, text=text, tag="workdey-welcome")


def send_match_note(user: User, match) -> EmailOutbox:
    from workdey.timeutil import utcnow

    opp = match.opportunity
    name = first_name(user)
    role = (opp.title_guess or "A role that fits")[:80]
    city = opp.location_guess or ""
    reason = (match.fit_reasons or ["It lines up with your profile."])[0]
    source = {"x": "X", "linkedin": "LinkedIn", "instagram": "Instagram", "workdey": "WorkDey"}.get(opp.source, opp.source)
    post_url = (opp.external_url or "").strip() or match_url(match.deep_link_token)
    inbox = inbox_url(user)
    where = f" — {html.escape(city)}" if city else ""
    body_html = f"""
      <p>We found a role that lines up with your profile.</p>
      <p style="font-size:22px;line-height:1.3;color:#e8ebe4;margin:12px 0;"><strong>{html.escape(role)}</strong>{where}</p>
      <p>Why it fits: {html.escape(reason)}</p>
      <p>Source: {html.escape(source)}. The scrape is already in your inbox. Open the post, or jump into WorkDey and prompt Grok for a reply, a cover letter, or a CV tailored to this role.</p>
    """
    body_text = (
        f"We found a role that lines up with your profile.\n\n"
        f"{role}{(' — ' + city) if city else ''}\n"
        f"Why it fits: {reason}\n"
        f"Source: {source}.\n\n"
        "The scrape is already in your inbox. Open the post, or jump into WorkDey and prompt Grok for a reply, "
        "a cover letter, or a CV tailored to this role."
    )
    html_body, text = _wrap(
        name=name,
        body_html=body_html,
        body_text=body_text,
        buttons=[("Open the post", post_url), ("Open your inbox", inbox)],
        user=user,
    )
    subject = f"New match: {role[:24]}"[:50]
    row = send(user=user, subject=subject, html_body=html_body, text=text, match_id=match.id, tag="workdey-match")
    if row.status in {"sent", "skipped", "queued"}:
        match.emailed_at = utcnow()
    return row


def send_digest_note(user: User, matches: list) -> EmailOutbox:
    from workdey.timeutil import utcnow

    if len(matches) == 1:
        return send_match_note(user, matches[0])
    name = first_name(user)
    n = len(matches)
    first = matches[0].opportunity.title_guess or "a role"
    inbox = inbox_url(user)
    post_url = (matches[0].opportunity.external_url or "").strip() or match_url(matches[0].deep_link_token)
    body_html = f"""
      <p>{n} new matches are waiting in your inbox — already scraped, ready for a reply, cover letter, or CV.</p>
      <p style="font-size:20px;color:#e8ebe4;"><strong>{html.escape(first)}</strong> and {n - 1} more.</p>
    """
    body_text = (
        f"{n} new matches are waiting in your inbox — already scraped, ready for a reply, cover letter, or CV.\n\n"
        f"{first} and {n - 1} more."
    )
    html_body, text = _wrap(
        name=name,
        body_html=body_html,
        body_text=body_text,
        buttons=[("Open the post", post_url), ("Open your inbox", inbox)],
        user=user,
    )
    row = send(user=user, subject=f"{n} new matches waiting in WorkDey"[:50], html_body=html_body, text=text, match_id=matches[0].id, tag="workdey-digest")
    if row.status in {"sent", "skipped", "queued"}:
        for m in matches:
            m.emailed_at = utcnow()
    return row
