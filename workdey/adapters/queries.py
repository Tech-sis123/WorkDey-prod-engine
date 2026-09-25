"""Build a small, high-yield search set from all active profiles + Nigerian seed lists."""

from __future__ import annotations

from workdey.models import Profile, Watch

SEED_X = [
    "hiring Nigeria",
    '"we are hiring" Lagos',
    '"we\'re hiring" Lagos',
    "#hiringnigeria",
    "#JobsinNigeria",
    "send CV Lagos hiring",
    "virtual assistant hiring Nigeria",
    "data analyst hiring Lagos",
    "DM for pitch Lagos",
    "NYSC hiring",
]
SEED_LI_KEYWORDS = [
    "software engineer",
    "data analyst",
    "product designer",
    "accountant",
    "virtual assistant",
    "customer success",
]
SEED_IG = [
    "https://www.instagram.com/explore/tags/hiringnigeria/",
    "https://www.instagram.com/explore/tags/jobsinlagos/",
    "https://www.instagram.com/explore/tags/nigerianjobs/",
]
SEED_LI_POSTS = [
    "hiring Lagos",
    "we are hiring Nigeria",
    "send your CV Lagos",
]


def active_profiles() -> list[Profile]:
    rows = (
        Profile.query.join(Watch, Watch.user_id == Profile.user_id)
        .filter(Watch.enabled.is_(True))
        .all()
    )
    return rows


def x_search_terms(max_terms: int = 12) -> list[str]:
    terms = list(SEED_X)
    for p in active_profiles():
        for role in (p.target_roles or [])[:3]:
            terms.append(f"{role} hiring Nigeria")
            terms.append(f"{role} Lagos")
        loc = (p.locations or ["Lagos"])[0]
        if loc.lower() not in {"remote", "nigeria"}:
            terms.append(f"hiring {loc}")
    # de-dupe, keep order
    seen = set()
    out = []
    for t in terms:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= max_terms:
            break
    return out


def linkedin_keyword_locations() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    roles = list(SEED_LI_KEYWORDS)
    locs = ["Lagos", "Nigeria"]
    for p in active_profiles():
        roles.extend(p.target_roles or [])
        locs.extend(p.locations or [])
    seen = set()
    for role in roles:
        loc = next((l for l in locs if l.lower() not in {"remote"}), "Lagos")
        key = (role.lower(), loc.lower())
        if key in seen or not role.strip():
            continue
        seen.add(key)
        pairs.append((role.strip(), loc))
        if len(pairs) >= 8:
            break
    return pairs


def instagram_urls() -> list[str]:
    return list(SEED_IG)


def linkedin_post_queries() -> list[str]:
    q = list(SEED_LI_POSTS)
    for p in active_profiles():
        for role in (p.target_roles or [])[:2]:
            q.append(f"{role} hiring Nigeria")
    seen = set()
    out = []
    for t in q:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= 8:
            break
    return out
