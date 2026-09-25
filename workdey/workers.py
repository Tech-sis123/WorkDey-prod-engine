"""Powerful scheduler + pinger.

Do not spawn one cron per user. A worker claims due watches every tick.
The pinger is a dead-man's switch: if the scheduler stalls, it restarts it,
records heartbeats, and optionally pings an external keepalive URL so free
hosts do not sleep.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import Config
from workdey.pipeline import beat, run_due_watches
from workdey.timeutil import utcnow

log = logging.getLogger("workdey.workers")

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()
_app = None


def _ctx(fn):
    def wrapped():
        if _app is None:
            return
        with _app.app_context():
            try:
                fn()
            except Exception:
                log.exception("job %s failed", fn.__name__)
                beat(fn.__name__, False, "exception")

    wrapped.__name__ = fn.__name__
    return wrapped


@_ctx
def job_match():
    result = run_due_watches()
    log.info("match tick %s", result)


@_ctx
def job_pinger():
    """Health pinger — watchdog, source liveness, optional keepalive."""
    from workdey.models import Heartbeat, SourceRun

    now = utcnow()
    detail = {"ts": now.isoformat()}
    sched_ok = True
    hb = Heartbeat.query.get("matcher")
    if hb and hb.last_ok_at:
        age = (now - hb.last_ok_at).total_seconds()
        detail["matcher_age_s"] = int(age)
        if age > max(90, Config.MATCH_TICK_SECONDS * 4):
            sched_ok = False
            detail["stalled"] = True
            restart_scheduler()
    # source freshness
    sources = {}
    for src in ("x", "linkedin", "linkedin_posts", "instagram", "workdey"):
        run = (
            SourceRun.query.filter_by(source=src)
            .order_by(SourceRun.started_at.desc())
            .first()
        )
        sources[src] = {
            "last": run.started_at.isoformat() if run and run.started_at else None,
            "status": run.status if run else "never",
        }
    detail["sources"] = sources
    if Config.KEEPALIVE_URL:
        try:
            r = requests.get(Config.KEEPALIVE_URL, timeout=8)
            detail["keepalive"] = r.status_code
        except Exception as exc:
            detail["keepalive_error"] = str(exc)[:160]
    # self-ping the local health route so reverse proxies see life
    try:
        requests.get(f"http://127.0.0.1:{Config.PORT}/health", timeout=4)
    except Exception:
        pass
    beat("pinger", sched_ok, "" if sched_ok else "scheduler stalled", **detail)


def restart_scheduler() -> None:
    global _scheduler
    with _lock:
        if _scheduler and _scheduler.running:
            try:
                _scheduler.wakeup()
            except Exception:
                pass
        beat("scheduler_restart", True)


def start_background(app) -> BackgroundScheduler:
    global _scheduler, _app
    _app = app
    with _lock:
        if _scheduler and _scheduler.running:
            return _scheduler
        sched = BackgroundScheduler(
            timezone=Config.TIMEZONE,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
        )
        sched.add_job(
            job_match,
            IntervalTrigger(seconds=Config.MATCH_TICK_SECONDS),
            id="match_tick",
            replace_existing=True,
        )
        sched.add_job(
            job_pinger,
            IntervalTrigger(seconds=Config.PING_EVERY_SECONDS),
            id="pinger",
            replace_existing=True,
        )
        sched.start()
        _scheduler = sched
        with app.app_context():
            beat("scheduler", True, started=utcnow().isoformat())
        log.info(
            "scheduler up match=%ss pinger=%ss",
            Config.MATCH_TICK_SECONDS,
            Config.PING_EVERY_SECONDS,
        )
        return sched


def scheduler_status() -> dict:
    s = _scheduler
    jobs = []
    if s:
        for j in s.get_jobs():
            jobs.append(
                {
                    "id": j.id,
                    "next": j.next_run_time.isoformat() if j.next_run_time else None,
                }
            )
    return {"running": bool(s and s.running), "jobs": jobs}
