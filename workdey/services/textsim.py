"""Lexical similarity — no paid embedding API required for v1 matching."""

from __future__ import annotations

import math
import re
from collections import Counter

STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "with", "at",
    "by", "from", "is", "are", "be", "as", "we", "you", "our", "your", "this",
    "that", "it", "will", "can", "if", "dm", "please", "role", "job", "jobs",
}

TOKEN = re.compile(r"[a-z0-9+#.]{2,}")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall((text or "").lower()) if t not in STOP]


def vector(text: str) -> Counter:
    return Counter(tokenize(text))


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    num = sum(a[k] * b[k] for k in keys)
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def overlap(needles: list[str], hay: str) -> list[str]:
    low = hay.lower()
    hits = []
    for n in needles:
        n = (n or "").strip()
        if len(n) < 2:
            continue
        if n.lower() in low:
            hits.append(n)
    return hits
