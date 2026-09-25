"""Match alerts. Short updates only. All mail goes out as WorkDey."""

from __future__ import annotations

from config import Config
from workdey.models import EmailOutbox, Match, User, Watch
from workdey.services.mailer import send_digest_note, send_match_note
from workdey.timeutil import local_now


def emails_today(watch: Watch) -> int:
    today = local_now(Config.TIMEZONE).date().isoformat()
    if watch.emails_sent_on != today:
        watch.emails_sent_on = today
        watch.emails_sent_count = 0
    return watch.emails_sent_count


def can_email(watch: Watch) -> bool:
    if not watch.email_on or not watch.enabled:
        return False
    if watch.alert_every_match:
        return True
    return emails_today(watch) < Config.EMAIL_DAILY_CAP


def send_match_email(user: User, match: Match) -> EmailOutbox:
    return send_match_note(user, match)


def send_digest(user: User, matches: list[Match]) -> EmailOutbox | None:
    if not matches:
        return None
    return send_digest_note(user, matches)
