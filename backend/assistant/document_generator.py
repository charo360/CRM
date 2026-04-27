"""
document_generator.py
Converts Claude's markdown output into polished PDF and Word documents.
Input: plain markdown string (what the assistant already produces).
"""
from __future__ import annotations

import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

TEMP_DIR = Path(tempfile.gettempdir()) / "zilo_docs"
TEMP_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Shared markdown parser  (uses stdlib `markdown`)
# ─────────────────────────────────────────────────────────────────────────────
def _md_to_html(md: str) -> str:
    import markdown as _md
    return _md.markdown(
        md,
        extensions=["tables", "fenced_code", "nl2br", "sane_lists"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Block-level token walker
# ─────────────────────────────────────────────────────────────────────────────
_BLOCK_RE = re.compile(
    r"(<h[1-6][^>]*>.*?</h[1-6]>|"
    r"<pre><code[^>]*>.*?</code></pre>|"
    r"<table>.*?</table>|"
    r"<ul>.*?</ul>|"
    r"<ol>.*?</ol>|"
    r"<hr\s*/?>|"
    r"<p>.*?</p>)",
    re.DOTALL,
)


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def _parse_blocks(html: str) -> List[Tuple[str, str]]:
    """Return list of (type, raw_html) tuples."""
    blocks: List[Tuple[str, str]] = []
    for m in _BLOCK_RE.finditer(html):
        raw = m.group(0).strip()
        if raw.startswith("<h1"):
            blocks.append(("h1", raw))
        elif raw.startswith("<h2"):
            blocks.append(("h2", raw))
        elif raw.startswith("<h3"):
            blocks.append(("h3", raw))
        elif raw.startswith("<h4") or raw.startswith("<h5") or raw.startswith("<h6"):
            blocks.append(("h4", raw))
        elif raw.startswith("<pre"):
            code = re.sub(r"</?(?:pre|code)[^>]*>", "", raw).strip()
            blocks.append(("code", code))
        elif raw.startswith("<table"):
            blocks.append(("table", raw))
        elif raw.startswith("<ul"):
            items = re.findall(r"<li>(.*?)</li>", raw, re.DOTALL)
            for item in items:
                blocks.append(("ul", _strip(item)))
        elif raw.startswith("<ol"):
            items = re.findall(r"<li>(.*?)</li>", raw, re.DOTALL)
            for i, item in enumerate(items):
                blocks.append(("ol", f"{i + 1}. {_strip(item)}"))
        elif re.match(r"<hr", raw):
            blocks.append(("hr", ""))
        elif raw.startswith("<p"):
            text = _strip(raw)
            if text:
                blocks.append(("p", text))
    return blocks


def _parse_table(raw: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", raw, re.DOTALL):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        rows.append([_strip(c) for c in cells])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Style helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_fonts(font_style: str) -> tuple[str, str]:
    """Return (body_font, bold_font) ReportLab names for a style keyword."""
    style = (font_style or "").lower()
    if style in ("serif", "classic"):
        return "Times-Roman", "Times-Bold"
    # sans-serif / modern / minimal / default
    return "Helvetica", "Helvetica-Bold"


def _safe_hex(hex_str: str, fallback: str) -> str:
    """Return hex_str if it looks like a valid hex colour, else fallback."""
    h = (hex_str or "").strip()
    if re.match(r"^#[0-9A-Fa-f]{3,8}$", h):
        return h
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# PDF  (reportlab)
# ─────────────────────────────────────────────────────────────────────────────
def generate_pdf(
    markdown_content: str,
    filename: str | None = None,
    business_name: str = "",
    style: dict | None = None,
) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    style = style or {}

    filename = filename or f"zilo_{uuid.uuid4().hex[:8]}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    filepath = TEMP_DIR / filename

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=2.2 * cm,
        leftMargin=2.2 * cm,
        topMargin=2.4 * cm,
        bottomMargin=2.2 * cm,
        title=filename.replace(".pdf", ""),
        author=business_name or "Zilo Chat",
    )

    # ── colour palette — use saved brand colors when available ───────────────
    PRIMARY_HEX   = _safe_hex(style.get("primary_color", ""), "#4F46E5")
    SECONDARY_HEX = _safe_hex(style.get("secondary_color", ""), "#EEF2FF")

    ACCENT      = colors.HexColor(PRIMARY_HEX)
    TABLE_HEAD  = colors.HexColor(SECONDARY_HEX)
    INK         = colors.HexColor("#111827")
    BODY        = colors.HexColor("#374151")
    MUTED       = colors.HexColor("#6B7280")
    RULE        = colors.HexColor("#E5E7EB")
    CODE_BG     = colors.HexColor("#F3F4F6")
    TABLE_ALT   = colors.HexColor("#F9FAFB")

    # ── fonts — serif vs sans-serif based on style profile ──────────────────
    BODY_FONT, BOLD_FONT = _resolve_fonts(style.get("font_style", ""))

    base = getSampleStyleSheet()

    def _s(**kw) -> ParagraphStyle:
        parent = kw.pop("parent", base["Normal"])
        name = kw.pop("name")
        return ParagraphStyle(name, parent=parent, **kw)

    H1   = _s(name="ZH1",   parent=base["Title"],   fontSize=22, leading=28, spaceAfter=4,  textColor=INK,   fontName=BOLD_FONT)
    H2   = _s(name="ZH2",   parent=base["Heading2"], fontSize=16, leading=20, spaceBefore=18, spaceAfter=4,  textColor=INK,   fontName=BOLD_FONT)
    H3   = _s(name="ZH3",   parent=base["Heading3"], fontSize=13, leading=17, spaceBefore=12, spaceAfter=3,  textColor=INK,   fontName=BOLD_FONT)
    H4   = _s(name="ZH4",   parent=base["Heading4"], fontSize=11, leading=15, spaceBefore=10, spaceAfter=2,  textColor=ACCENT, fontName=BOLD_FONT)
    BP   = _s(name="ZBP",   fontSize=11, leading=17, spaceAfter=7,  textColor=BODY, fontName=BODY_FONT)
    LI   = _s(name="ZLI",   fontSize=11, leading=17, spaceAfter=3,  textColor=BODY, fontName=BODY_FONT, leftIndent=16, bulletIndent=4)
    SIG  = _s(name="ZSig",  fontSize=10, leading=14, spaceAfter=2,  textColor=INK,  fontName=BOLD_FONT)
    SIG2 = _s(name="ZSig2", fontSize=9,  leading=13, spaceAfter=1,  textColor=MUTED, fontName=BODY_FONT)
    HDR  = _s(name="ZHdr",  fontSize=8,  leading=11, spaceAfter=0,  textColor=MUTED, fontName=BODY_FONT, alignment=2)
    CODE = _s(name="ZCode", fontSize=9,  leading=13, spaceAfter=8,  textColor=colors.HexColor("#1E293B"),
              fontName="Courier", leftIndent=12, backColor=CODE_BG, borderPadding=6)
    FTR  = _s(name="ZFtr",  fontSize=8.5, leading=12, textColor=MUTED, fontName=BODY_FONT, alignment=1)

    story = []

    # ── Header text (top-right, from style profile) ──────────────────────────
    header_text = (style.get("header_text") or "").strip()
    if header_text:
        story.append(Paragraph(header_text, HDR))
        story.append(Spacer(1, 6))

    html = _md_to_html(markdown_content)
    blocks = _parse_blocks(html)

    # inline bold/italic helper
    def _inline(text: str) -> str:
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        text = re.sub(r"`(.*?)`", r"<font name='Courier' size='9'>\1</font>", text)
        return text

    for kind, raw in blocks:
        if kind == "h1":
            story.append(Paragraph(_strip(raw), H1))
            story.append(HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=10))
        elif kind == "h2":
            story.append(Paragraph(_strip(raw), H2))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=6))
        elif kind == "h3":
            story.append(Paragraph(_strip(raw), H3))
        elif kind == "h4":
            story.append(Paragraph(_strip(raw), H4))
        elif kind == "hr":
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=8))
        elif kind == "code":
            story.append(Spacer(1, 2))
            story.append(Paragraph(raw.replace("\n", "<br/>"), CODE))
        elif kind == "ul":
            story.append(Paragraph(f"• {_inline(raw)}", LI))
        elif kind == "ol":
            story.append(Paragraph(_inline(raw), LI))
        elif kind == "table":
            rows = _parse_table(raw)
            if rows:
                ncols = max(len(r) for r in rows)
                rows = [r + [""] * (ncols - len(r)) for r in rows]
                col_w = (A4[0] - 4.4 * cm) / ncols
                tbl = Table(rows, colWidths=[col_w] * ncols, repeatRows=1)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, 0),  TABLE_HEAD),
                    ("TEXTCOLOR",     (0, 0), (-1, 0),  INK),
                    ("FONTNAME",      (0, 0), (-1, 0),  BOLD_FONT),
                    ("FONTSIZE",      (0, 0), (-1, 0),  10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0),  8),
                    ("TOPPADDING",    (0, 0), (-1, 0),  8),
                    ("FONTNAME",      (0, 1), (-1, -1), BODY_FONT),
                    ("FONTSIZE",      (0, 1), (-1, -1), 10),
                    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, TABLE_ALT]),
                    ("PADDING",       (0, 1), (-1, -1), 6),
                    ("GRID",          (0, 0), (-1, -1), 0.4, RULE),
                    ("LINEBELOW",     (0, 0), (-1, 0),  1,   ACCENT),
                    ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 10))
        elif kind == "p":
            story.append(Paragraph(_inline(raw), BP))

    # ── Signature block (from style profile) ────────────────────────────────
    sig_name    = (style.get("signature_name") or "").strip()
    sig_title   = (style.get("signature_title") or "").strip()
    sig_contact = (style.get("signature_contact") or "").strip()
    if sig_name or sig_title or sig_contact:
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="40%", thickness=0.6, color=ACCENT, spaceAfter=8))
        if sig_name:
            story.append(Paragraph(sig_name, SIG))
        if sig_title:
            story.append(Paragraph(sig_title, SIG2))
        if sig_contact:
            story.append(Paragraph(sig_contact, SIG2))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.4, color=RULE, spaceAfter=6))
    footer_text = (style.get("footer_text") or "").strip()
    footer_line = footer_text or f"Generated by <b>Zilo Chat</b> · {business_name or ''}"
    footer_line += f" · {datetime.utcnow().strftime('%d %b %Y')}"
    story.append(Paragraph(footer_line, FTR))

    doc.build(story)
    return str(filepath)


# ─────────────────────────────────────────────────────────────────────────────
# DOCX  (python-docx)
# ─────────────────────────────────────────────────────────────────────────────
def generate_docx(markdown_content: str, filename: str | None = None) -> str:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    filename = filename or f"zilo_{uuid.uuid4().hex[:8]}.docx"
    if not filename.endswith(".docx"):
        filename += ".docx"
    filepath = TEMP_DIR / filename

    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.4)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # ── helper: set paragraph spacing ──────────────────────────────────────
    def _spacing(para, before: int = 0, after: int = 6, line: int = 276):
        pPr = para._p.get_or_add_pPr()
        spg = OxmlElement("w:spacing")
        spg.set(qn("w:before"), str(before))
        spg.set(qn("w:after"), str(after))
        spg.set(qn("w:line"), str(line))
        spg.set(qn("w:lineRule"), "auto")
        pPr.append(spg)

    # ── helper: add horizontal rule ─────────────────────────────────────────
    def _add_rule(para):
        pPr = para._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "E5E7EB")
        pBdr.append(bottom)
        pPr.append(pBdr)

    # ── helper: table shading ───────────────────────────────────────────────
    def _shade_cell(cell, hex_color: str):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)

    html = _md_to_html(markdown_content)
    blocks = _parse_blocks(html)

    _OL_CTR = 0
    for kind, raw in blocks:
        if kind == "h1":
            p = doc.add_heading(_strip(raw), level=1)
            p.runs[0].font.color.rgb = RGBColor(0x11, 0x18, 0x27)
            p.runs[0].font.size = Pt(22)
            _add_rule(p)
            _spacing(p, before=0, after=120)
        elif kind == "h2":
            p = doc.add_heading(_strip(raw), level=2)
            p.runs[0].font.color.rgb = RGBColor(0x11, 0x18, 0x27)
            p.runs[0].font.size = Pt(16)
            _add_rule(p)
            _spacing(p, before=240, after=80)
        elif kind == "h3":
            p = doc.add_heading(_strip(raw), level=3)
            p.runs[0].font.size = Pt(13)
            _spacing(p, before=160, after=60)
        elif kind == "h4":
            p = doc.add_heading(_strip(raw), level=4)
            p.runs[0].font.size = Pt(11)
            p.runs[0].font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)
        elif kind == "hr":
            p = doc.add_paragraph()
            _add_rule(p)
        elif kind == "code":
            p = doc.add_paragraph(raw)
            p.style = doc.styles["Normal"]
            for run in p.runs:
                run.font.name = "Courier New"
                run.font.size = Pt(9)
                run.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)
            # light-gray shading for code block paragraph
            _shade_cell_like_para = OxmlElement("w:pPr")
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F3F4F6")
            rPr = OxmlElement("w:rPr")
            _shade_cell_like_para.append(shd)
            p._p.insert(0, _shade_cell_like_para)
        elif kind == "ul":
            p = doc.add_paragraph(raw, style="List Bullet")
            _spacing(p, before=0, after=40)
        elif kind == "ol":
            p = doc.add_paragraph(raw, style="List Number")
            _spacing(p, before=0, after=40)
        elif kind == "table":
            rows = _parse_table(raw)
            if rows and rows[0]:
                ncols = max(len(r) for r in rows)
                rows = [r + [""] * (ncols - len(r)) for r in rows]
                tbl = doc.add_table(rows=len(rows), cols=ncols)
                tbl.style = "Table Grid"
                for i, row_data in enumerate(rows):
                    for j, text in enumerate(row_data):
                        cell = tbl.rows[i].cells[j]
                        cell.text = text
                        para = cell.paragraphs[0]
                        if i == 0:
                            # Header row
                            _shade_cell(cell, "EEF2FF")
                            if para.runs:
                                para.runs[0].bold = True
                                para.runs[0].font.color.rgb = RGBColor(0x11, 0x18, 0x27)
                        elif i % 2 == 0:
                            _shade_cell(cell, "F9FAFB")
                doc.add_paragraph()
        elif kind == "p":
            p = doc.add_paragraph(raw)
            _spacing(p, before=0, after=80)

    # ── Footer ───────────────────────────────────────────────────────────────
    doc.add_paragraph()
    footer_p = doc.add_paragraph(
        f"Generated by Zilo Chat · {datetime.utcnow().strftime('%d %b %Y, %H:%M')} UTC"
    )
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if footer_p.runs:
        footer_p.runs[0].font.size = Pt(8.5)
        footer_p.runs[0].font.color.rgb = RGBColor(0x6B, 0x72, 0x80)

    doc.save(str(filepath))
    return str(filepath)


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup helper
# ─────────────────────────────────────────────────────────────────────────────
def cleanup_file(filepath: str) -> None:
    try:
        os.remove(filepath)
    except Exception:
        pass
