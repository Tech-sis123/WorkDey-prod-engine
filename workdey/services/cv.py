"""CV upload parse — PDF / DOCX to text, then a light skills/education draft."""

from __future__ import annotations

import io
import re
from pathlib import Path

SKILL_LINE = re.compile(r"(skills?|stack|tools?)\s*[:\-]\s*(.+)", re.I)
EDU_HINT = re.compile(
    r"\b(bsc|b\.sc|hnd|ond|msc|mba|nysc|university|polytechnic|degree)\b", re.I
)


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        return _pdf(data)
    if name.endswith(".docx") or name.endswith(".doc"):
        return _docx(data)
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:8]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _docx(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def draft_fields(text: str) -> dict:
    skills: list[str] = []
    education = ""
    years = 0
    for line in (text or "").splitlines():
        m = SKILL_LINE.search(line)
        if m:
            skills.extend([s.strip() for s in re.split(r"[,/|•;]", m.group(2)) if s.strip()])
        if EDU_HINT.search(line) and len(line.strip()) < 180:
            education = education or line.strip()
    ym = re.search(r"(\d{1,2})\+?\s+years?", text or "", re.I)
    if ym:
        years = min(40, int(ym.group(1)))
    # common Nigerian / tech tokens sitting in the blob
    bag = {
        "excel", "python", "sql", "figma", "javascript", "react", "excel",
        "bookkeeping", "quickbooks", "power bi", "tableau", "canva",
        "customer service", "salesforce", "wordpress", "excel",
    }
    low = (text or "").lower()
    for token in bag:
        if token in low and token.title() not in skills and token not in [s.lower() for s in skills]:
            skills.append(token)
    # unique preserve order
    seen = set()
    tags = []
    for s in skills:
        k = s.lower()
        if k in seen or len(s) < 2:
            continue
        seen.add(k)
        tags.append(s[:40])
        if len(tags) >= 16:
            break
    return {"skills_tags": tags, "education": education[:240], "years_experience": years}


def save_upload(upload_dir: Path, user_id: str, filename: str, data: bytes) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower() or ".bin"
    if ext not in {".pdf", ".docx", ".doc", ".txt"}:
        ext = ".bin"
    path = upload_dir / f"{user_id}{ext}"
    path.write_bytes(data)
    return path
