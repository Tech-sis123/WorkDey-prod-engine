from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workdey.db import db
from workdey.timeutil import utcnow


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(10)}"


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("usr"))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    unsub_token: Mapped[str] = mapped_column(String(48), unique=True, default=lambda: secrets.token_urlsafe(18))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False)
    watch: Mapped["Watch"] = relationship(back_populates="user", uselist=False)
    matches: Mapped[list["Match"]] = relationship(back_populates="user")


class Profile(db.Model):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("prf"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    skills_text: Mapped[str] = mapped_column(Text, default="")
    skills_tags: Mapped[list] = mapped_column(db.JSON, default=list)
    education: Mapped[str] = mapped_column(Text, default="")
    years_experience: Mapped[int] = mapped_column(Integer, default=0)
    target_roles: Mapped[list] = mapped_column(db.JSON, default=list)
    locations: Mapped[list] = mapped_column(db.JSON, default=list)
    work_type: Mapped[str] = mapped_column(String(24), default="either")
    paid_only: Mapped[bool] = mapped_column(Boolean, default=True)
    seniority: Mapped[str] = mapped_column(String(24), default="mid")
    summary: Mapped[str] = mapped_column(Text, default="")
    linkedin_url: Mapped[str] = mapped_column(String(300), default="")
    x_handle: Mapped[str] = mapped_column(String(80), default="")
    cv_path: Mapped[str] = mapped_column(String(400), default="")
    cv_text: Mapped[str] = mapped_column(Text, default="")
    completeness: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="profile")

    def completeness_score(self) -> int:
        score = 0
        if self.skills_tags or self.skills_text:
            score += 25
        if self.education:
            score += 15
        if self.target_roles:
            score += 20
        if self.locations:
            score += 10
        if self.years_experience is not None:
            score += 10
        if self.cv_text:
            score += 15
        if self.summary:
            score += 5
        self.completeness = min(score, 100)
        return self.completeness


class Watch(db.Model):
    __tablename__ = "watches"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("wch"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cadence_hours: Mapped[int] = mapped_column(Integer, default=24)
    quiet_start: Mapped[str] = mapped_column(String(8), default="21:00")
    quiet_end: Mapped[str] = mapped_column(String(8), default="07:00")
    email_on: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_every_match: Mapped[bool] = mapped_column(Boolean, default=False)
    sources: Mapped[dict] = mapped_column(
        db.JSON,
        default=lambda: {"x": True, "linkedin": True, "instagram": True, "workdey": True},
    )
    paused_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    emails_sent_on: Mapped[str] = mapped_column(String(16), default="")
    emails_sent_count: Mapped[int] = mapped_column(Integer, default=0)
    match_threshold: Mapped[float] = mapped_column(Float, default=0.42)

    user: Mapped[User] = relationship(back_populates="watch")


class Opportunity(db.Model):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("opp"))
    source: Mapped[str] = mapped_column(String(24), index=True)
    external_id: Mapped[str] = mapped_column(String(180), default="", index=True)
    external_url: Mapped[str] = mapped_column(String(600), default="")
    author_handle: Mapped[str] = mapped_column(String(180), default="")
    author_name: Mapped[str] = mapped_column(String(180), default="")
    title_guess: Mapped[str] = mapped_column(String(240), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    location_guess: Mapped[str] = mapped_column(String(120), default="")
    employment_type_guess: Mapped[str] = mapped_column(String(40), default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lang: Mapped[str] = mapped_column(String(12), default="en")
    job_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    scam_risk: Mapped[float] = mapped_column(Float, default=0.0)
    classification: Mapped[str] = mapped_column(String(24), default="job")
    has_media: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_snapshot: Mapped[dict] = mapped_column(db.JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    verified_employer: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    killed: Mapped[bool] = mapped_column(Boolean, default=False)


class Match(db.Model):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("mch"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    fit_score: Mapped[float] = mapped_column(Float, default=0.0)
    fit_reasons: Mapped[list] = mapped_column(db.JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="new", index=True)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    deep_link_token: Mapped[str] = mapped_column(String(48), unique=True, default=lambda: secrets.token_urlsafe(16))

    user: Mapped[User] = relationship(back_populates="matches")
    opportunity: Mapped[Opportunity] = relationship()
    drafts: Mapped[list["Draft"]] = relationship(back_populates="match")


class Draft(db.Model):
    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("dft"))
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    body: Mapped[str] = mapped_column(Text, default="")
    facts_used: Mapped[list] = mapped_column(db.JSON, default=list)
    note: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    match: Mapped[Match] = relationship(back_populates="drafts")


class EmailOutbox(db.Model):
    __tablename__ = "email_outbox"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("eml"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("matches.id"), nullable=True)
    to_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(200))
    html: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    provider_id: Mapped[str] = mapped_column(String(120), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Report(db.Model):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("rpt"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.id"))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SourceRun(db.Model):
    __tablename__ = "source_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _id("run"))
    source: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running")
    items_in: Mapped[int] = mapped_column(Integer, default=0)
    items_kept: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    apify_run_id: Mapped[str] = mapped_column(String(80), default="")


class Setting(db.Model):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Heartbeat(db.Model):
    __tablename__ = "heartbeats"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_ok_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_error: Mapped[str] = mapped_column(Text, default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    detail: Mapped[dict] = mapped_column(db.JSON, default=dict)


class MagicToken(db.Model):
    __tablename__ = "magic_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(24), default="login")
    match_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
