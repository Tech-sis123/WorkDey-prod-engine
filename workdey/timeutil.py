from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def tzinfo(name: str = "Africa/Lagos") -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def utcnow() -> datetime:
    # naive UTC — SQLite-friendly, compared only against other naive UTC values
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def local_now(tz_name: str = "Africa/Lagos") -> datetime:
    return datetime.now(timezone.utc).astimezone(tzinfo(tz_name))


def skip_quiet_hours(
    when: datetime,
    quiet_start: str | None,
    quiet_end: str | None,
    tz_name: str = "Africa/Lagos",
) -> datetime:
    """Push `when` forward if it lands inside the user's quiet window (WAT)."""
    if not quiet_start or not quiet_end:
        return when
    try:
        qs = _parse_hhmm(quiet_start)
        qe = _parse_hhmm(quiet_end)
    except ValueError:
        return when
    aware = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when
    local = aware.astimezone(tzinfo(tz_name))
    start_dt = local.replace(hour=qs.hour, minute=qs.minute, second=0, microsecond=0)
    end_dt = local.replace(hour=qe.hour, minute=qe.minute, second=0, microsecond=0)
    if qs <= qe:
        in_quiet = start_dt <= local < end_dt
        if in_quiet:
            return end_dt.astimezone(timezone.utc).replace(tzinfo=None)
        return when
    in_quiet = local >= start_dt or local < end_dt
    if not in_quiet:
        return when
    if local >= start_dt:
        return (end_dt + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
    return end_dt.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()
