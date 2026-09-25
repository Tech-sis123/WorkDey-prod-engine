"""One-page PDF export for cover letters and CV revamps."""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def render_letter(title: str, body: str, footer: str = "WorkDey draft — review before sending.") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left, right = 22 * mm, width - 22 * mm
    y = height - 24 * mm
    c.setFillColorRGB(0.08, 0.09, 0.08)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    c.setFillColorRGB(0.84, 0.87, 0.83)
    c.setFont("Times-Bold", 16)
    for line in _wrap(title, 78):
        c.drawString(left, y, line)
        y -= 18
    y -= 8
    c.setStrokeColorRGB(0.3, 0.32, 0.3)
    c.line(left, y, right, y)
    y -= 20
    c.setFillColorRGB(0.91, 0.92, 0.89)
    c.setFont("Times-Roman", 11)
    for para in body.split("\n"):
        if not para.strip():
            y -= 10
            continue
        for line in _wrap(para, 92):
            if y < 28 * mm:
                c.showPage()
                c.setFillColorRGB(0.08, 0.09, 0.08)
                c.rect(0, 0, width, height, fill=1, stroke=0)
                c.setFillColorRGB(0.91, 0.92, 0.89)
                c.setFont("Times-Roman", 11)
                y = height - 24 * mm
            c.drawString(left, y, line)
            y -= 14
    c.setFont("Times-Italic", 8)
    c.setFillColorRGB(0.55, 0.58, 0.53)
    c.drawString(left, 16 * mm, footer)
    c.save()
    return buf.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > width:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]
