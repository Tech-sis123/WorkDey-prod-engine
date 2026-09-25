"""Source adapters. Each one is isolatable — a kill-switch takes it down without touching the rest."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from config import Config
from workdey.adapters import queries
from workdey.adapters.apify import ApifyError, run_actor
from workdey.models import Setting
from workdey.services.classifier import classify
from workdey.services.matcher import fingerprint
from workdey.timeutil import to_utc

log = logging.getLogger("workdey.sources")


def _kill_switch(source: str) -> bool:
    row = Setting.query.get(f"kill.{source}")
    if row and row.value in {"1", "true", "on"}:
        return True
    return not Config.SOURCE_FLAGS.get(source, True)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None
    s = str(value).replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            if fmt is None:
                return to_utc(datetime.fromisoformat(s[:32]))
            return to_utc(datetime.strptime(s[:19], fmt))
        except Exception:
            continue
    return None


def normalize(
    *,
    source: str,
    url: str,
    title: str,
    body: str,
    author: str = "",
    author_name: str = "",
    location: str = "",
    posted_at: Any = None,
    raw: dict | None = None,
    verified: bool = False,
    has_media: bool = False,
    external_id: str = "",
    employment: str = "",
) -> dict:
    c = classify(title, body, source)
    loc = location or c.location_guess
    title_g = title or c.title_guess
    return {
        "source": "linkedin" if source == "linkedin_posts" else source,
        "adapter": source,
        "external_id": external_id or url,
        "external_url": url,
        "author_handle": (author or "")[:180],
        "author_name": (author_name or "")[:180],
        "title_guess": title_g[:240],
        "body": (body or "")[:8000],
        "location_guess": (loc or "")[:120],
        "employment_type_guess": employment or c.employment_type_guess,
        "posted_at": _parse_dt(posted_at),
        "lang": "en",
        "job_confidence": c.job_confidence,
        "scam_risk": c.scam_risk,
        "classification": c.classification,
        "has_media": has_media,
        "raw_snapshot": (raw or {}) if isinstance(raw, dict) else {},
        "fingerprint": fingerprint(source, url, title_g, body or ""),
        "verified_employer": verified,
    }


# ---------- X / Twitter ----------

def harvest_x(token: str, max_items: int) -> tuple[str, list[dict]]:
    if _kill_switch("x"):
        return "", []
    terms = queries.x_search_terms()
    actor_input = {
        "searchTerms": terms,
        "sort": "Latest",
        "maxItems": max_items,
        "tweetLanguage": "en",
    }
    run_id, items = run_actor(token, Config.ACTORS["x"], actor_input)
    out = []
    for it in items:
        text = it.get("fullText") or it.get("text") or it.get("content") or ""
        url = it.get("url") or it.get("twitterUrl") or ""
        if not url and it.get("id"):
            user = (it.get("author") or it.get("user") or {})
            handle = user.get("userName") or user.get("username") or "i"
            url = f"https://x.com/{handle}/status/{it.get('id')}"
        author = it.get("author") if isinstance(it.get("author"), dict) else {}
        handle = author.get("userName") or author.get("username") or it.get("username") or ""
        out.append(
            normalize(
                source="x",
                url=url,
                title="",
                body=text,
                author=handle,
                author_name=author.get("name") or "",
                posted_at=it.get("createdAt") or it.get("created_at"),
                raw={"id": it.get("id"), "likeCount": it.get("likeCount")},
                has_media=bool(it.get("media") or it.get("extendedEntities")),
                external_id=str(it.get("id") or url),
            )
        )
    return run_id, out


# ---------- LinkedIn jobs ----------

def harvest_linkedin_jobs(token: str, max_items: int) -> tuple[str, list[dict]]:
    if _kill_switch("linkedin"):
        return "", []
    pairs = queries.linkedin_keyword_locations()
    keyword, location = pairs[0] if pairs else ("hiring", "Lagos")
    actor_input = {
        "keywords": keyword,
        "location": location,
        "datePosted": "r86400",
        "autoConvertToAiSearch": True,
        "count": max_items,
        "limit": max_items,
    }
    run_id, items = run_actor(token, Config.ACTORS["linkedin"], actor_input, wait_secs=240)
    out = []
    for it in items:
        title = it.get("title") or it.get("jobTitle") or ""
        body = it.get("descriptionText") or it.get("description") or it.get("jobDescription") or ""
        if it.get("descriptionHtml") and not body:
            body = it.get("descriptionHtml")
        url = it.get("link") or it.get("jobUrl") or it.get("url") or ""
        loc = it.get("location") or ""
        out.append(
            normalize(
                source="linkedin",
                url=url,
                title=title,
                body=body,
                author=it.get("companyName") or "",
                author_name=it.get("companyName") or "",
                location=loc,
                posted_at=it.get("postedAt") or it.get("publishedAt"),
                raw={"company": it.get("companyName"), "employmentType": it.get("employmentType")},
                verified=True,
                external_id=str(it.get("id") or url),
                employment=it.get("employmentType") or "",
            )
        )
    return run_id, out


# ---------- LinkedIn posts (informal hiring) ----------

def harvest_linkedin_posts(token: str, max_items: int) -> tuple[str, list[dict]]:
    if _kill_switch("linkedin_posts"):
        return "", []
    qs = queries.linkedin_post_queries()
    actor_input: dict[str, Any] = {
        "searchQueries": qs,
        "queries": qs,
        "limitPerSource": max(5, max_items // max(len(qs), 1)),
        "maxPosts": max_items,
        "deepScrape": False,
    }
    if Config.LINKEDIN_COOKIE:
        actor_input["cookie"] = Config.LINKEDIN_COOKIE
        actor_input["cookies"] = Config.LINKEDIN_COOKIE
    run_id, items = run_actor(token, Config.ACTORS["linkedin_posts"], actor_input, wait_secs=240)
    out = []
    for it in items:
        text = it.get("text") or it.get("content") or it.get("commentary") or it.get("postText") or ""
        url = it.get("url") or it.get("postUrl") or it.get("link") or ""
        author = it.get("author") or it.get("authorName") or it.get("authorProfile") or ""
        if isinstance(author, dict):
            handle = author.get("publicId") or author.get("name") or ""
            name = author.get("name") or ""
        else:
            handle, name = str(author), str(author)
        out.append(
            normalize(
                source="linkedin_posts",
                url=url,
                title="",
                body=text,
                author=handle,
                author_name=name,
                posted_at=it.get("postedAt") or it.get("time") or it.get("publishedAt"),
                raw={"urn": it.get("urn") or it.get("id")},
                external_id=str(it.get("urn") or it.get("id") or url),
            )
        )
    return run_id, out


# ---------- Instagram ----------

def harvest_instagram(token: str, max_items: int) -> tuple[str, list[dict]]:
    if _kill_switch("instagram"):
        return "", []
    actor_input = {
        "directUrls": queries.instagram_urls(),
        "resultsType": "posts",
        "resultsLimit": max_items,
        "searchLimit": max_items,
    }
    run_id, items = run_actor(token, Config.ACTORS["instagram"], actor_input, wait_secs=240)
    out = []
    for it in items:
        # hashtag search may nest posts
        posts = it.get("latestPosts") or it.get("posts")
        chunk = posts if isinstance(posts, list) else [it]
        for p in chunk:
            cap = p.get("caption") or p.get("text") or ""
            url = p.get("url") or p.get("displayUrl") or ""
            if p.get("shortCode") and not url:
                url = f"https://www.instagram.com/p/{p.get('shortCode')}/"
            out.append(
                normalize(
                    source="instagram",
                    url=url,
                    title="",
                    body=cap,
                    author=p.get("ownerUsername") or it.get("ownerUsername") or "",
                    author_name=p.get("ownerFullName") or "",
                    posted_at=p.get("timestamp") or p.get("takenAt"),
                    raw={"likes": p.get("likesCount")},
                    has_media=True,
                    external_id=str(p.get("id") or p.get("shortCode") or url),
                )
            )
    return run_id, out


HARVESTERS: dict[str, Callable[[str, int], tuple[str, list[dict]]]] = {
    "x": harvest_x,
    "linkedin": harvest_linkedin_jobs,
    "linkedin_posts": harvest_linkedin_posts,
    "instagram": harvest_instagram,
}
