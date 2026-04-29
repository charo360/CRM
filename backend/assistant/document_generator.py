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
# PDF  (reportlab)
# ─────────────────────────────────────────────────────────────────────────────
def generate_pdf(markdown_content: str, filename: str | None = None, business_name: str | None = None, style: dict | None = None, logo_url: str | None = None) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        HRFlowable,
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    filename = filename or f"zilo_{uuid.uuid4().hex[:8]}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    filepath = TEMP_DIR / filename

    # ── colour palette — respect saved style ─────────────────────────────────
    s = style or {}
    _pc = s.get("primary_color", "").strip().lstrip("#") or "4F46E5"
    _sc = s.get("secondary_color", "").strip().lstrip("#") or "818CF8"
    PRIMARY     = colors.HexColor(f"#{_pc}")
    PRIMARY_L   = colors.HexColor(f"#{_sc}")
    INK         = colors.HexColor("#111827")
    BODY        = colors.HexColor("#374151")
    MUTED       = colors.HexColor("#6B7280")
    RULE        = colors.HexColor("#E5E7EB")
    CODE_BG     = colors.HexColor("#F3F4F6")
    # Derive table head / alt from primary colour (light tint)
    TABLE_HEAD  = colors.HexColor(f"#{_sc[:2]}F2{_sc[2:]}" if len(_sc) == 6 else "#EEF2FF")
    TABLE_ALT   = colors.HexColor("#F9FAFB")
    COVER_BG    = PRIMARY

    # ── Download logo if available ────────────────────────────────────────────
    logo_path: str | None = None
    if logo_url:
        try:
            import httpx as _httpx
            import tempfile as _tf
            resp = _httpx.get(logo_url, timeout=10.0, follow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 100:
                _logo_tmp = _tf.NamedTemporaryFile(suffix=".png", delete=False)
                _logo_tmp.write(resp.content)
                _logo_tmp.close()
                logo_path = _logo_tmp.name
        except Exception:
            pass  # non-fatal — continue without logo

    # ── Extract title from first H1 ─────────────────────────────────────────
    html_full = _md_to_html(markdown_content)
    blocks = _parse_blocks(html_full)
    doc_title = "Document"
    for kind, raw in blocks:
        if kind == "h1":
            doc_title = _strip(raw)
            break

    # ── Page template with header/footer ─────────────────────────────────────
    page_w, page_h = A4

    # ── Logo placement from style ────────────────────────────────────────────
    _logo_placement = (s.get("logo_placement") or "top-left").lower()
    if _logo_placement == "none":
        _logo_placement = None

    def _header_footer(canvas, doc):
        canvas.saveState()
        # Header line on pages after the cover
        if doc.page > 1:
            canvas.setStrokeColor(RULE)
            canvas.setLineWidth(0.5)
            canvas.line(2.2 * cm, page_h - 1.8 * cm, page_w - 2.2 * cm, page_h - 1.8 * cm)
            # Logo in header if placement is top-left/top-right
            if logo_path and _logo_placement in ("top-left", "top-right"):
                try:
                    logo_w, logo_h = 24, 24
                    if _logo_placement == "top-left":
                        canvas.drawImage(logo_path, 2.2 * cm, page_h - 1.5 * cm - logo_h, logo_w, logo_h, mask="auto")
                        canvas.setFont(_body_font, 7.5)
                        canvas.setFillColor(MUTED)
                        canvas.drawString(2.2 * cm + logo_w + 4, page_h - 1.6 * cm, business_name or "")
                    else:
                        canvas.drawImage(logo_path, page_w - 2.2 * cm - logo_w, page_h - 1.5 * cm - logo_h, logo_w, logo_h, mask="auto")
                        canvas.setFont(_body_font, 7.5)
                        canvas.setFillColor(MUTED)
                        canvas.drawRightString(page_w - 2.2 * cm - logo_w - 4, page_h - 1.6 * cm, doc_title)
                except Exception:
                    pass
            else:
                canvas.setFont(_body_font, 7.5)
                canvas.setFillColor(MUTED)
                canvas.drawString(2.2 * cm, page_h - 1.6 * cm, business_name or "Zilo Chat")
                canvas.drawRightString(page_w - 2.2 * cm, page_h - 1.6 * cm, doc_title)
        # Footer with page number
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.3)
        canvas.line(2.2 * cm, 1.6 * cm, page_w - 2.2 * cm, 1.6 * cm)
        canvas.setFont(_body_font, 7.5)
        canvas.setFillColor(MUTED)
        if doc.page > 1:
            canvas.drawCentredString(page_w / 2, 1.0 * cm, f"Page {doc.page - 1}")
        canvas.drawRightString(page_w - 2.2 * cm, 1.0 * cm,
                               f"Generated via Zilo Chat · {datetime.utcnow().strftime('%d %b %Y')}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        rightMargin=2.2 * cm,
        leftMargin=2.2 * cm,
        topMargin=2.4 * cm,
        bottomMargin=2.2 * cm,
        title=doc_title,
        author=business_name or "Zilo Chat",
    )

    base = getSampleStyleSheet()

    def _s(**kw) -> ParagraphStyle:
        parent = kw.pop("parent", base["Normal"])
        name = kw.pop("name")
        return ParagraphStyle(name, parent=parent, **kw)

    # ── Font selection from style ────────────────────────────────────────────
    _fs = (s.get("font_style") or "").lower()
    if "serif" in _fs or "classic" in _fs:
        _heading_font = "Times-Bold"
        _body_font = "Times-Roman"
    else:
        _heading_font = "Helvetica-Bold"
        _body_font = "Helvetica"

    # ── Cover page styles ────────────────────────────────────────────────────
    COVER_TITLE = _s(name="ZCoverTitle", fontSize=28, leading=34, textColor=colors.white,
                     fontName=_heading_font, alignment=1, spaceAfter=12)
    COVER_SUB = _s(name="ZCoverSub", fontSize=13, leading=18, textColor=colors.HexColor(f"#{_sc}"),
                   fontName=_body_font, alignment=1, spaceAfter=6)
    COVER_DATE = _s(name="ZCoverDate", fontSize=10, leading=14, textColor=colors.HexColor(f"#{_sc}"),
                    fontName=_body_font, alignment=1)

    # ── Body styles ──────────────────────────────────────────────────────────
    H1 = _s(name="ZH1", parent=base["Title"],   fontSize=20, leading=26, spaceAfter=6,  textColor=INK, fontName=_heading_font)
    H2 = _s(name="ZH2", parent=base["Heading2"], fontSize=15, leading=19, spaceBefore=20, spaceAfter=6,  textColor=INK, fontName=_heading_font)
    H3 = _s(name="ZH3", parent=base["Heading3"], fontSize=12.5, leading=16, spaceBefore=14, spaceAfter=4,  textColor=INK, fontName=_heading_font)
    H4 = _s(name="ZH4", parent=base["Heading4"], fontSize=11, leading=15, spaceBefore=10, spaceAfter=2,  textColor=PRIMARY, fontName=_heading_font)
    BP = _s(name="ZBP", fontSize=10.5, leading=16.5, spaceAfter=7, textColor=BODY, fontName=_body_font)
    LI = _s(name="ZLI", fontSize=10.5, leading=16.5, spaceAfter=3, textColor=BODY, leftIndent=18, bulletIndent=4, fontName=_body_font)
    CODE = _s(name="ZCode", fontSize=9,  leading=13, spaceAfter=8, textColor=colors.HexColor("#1E293B"),
              fontName="Courier", leftIndent=12, backColor=CODE_BG, borderPadding=6)
    TBL_CELL = _s(name="ZTblCell", fontSize=9.5, leading=13, textColor=BODY, fontName=_body_font)
    TBL_HEAD_CELL = _s(name="ZTblHead", fontSize=9.5, leading=13, textColor=INK, fontName=_heading_font)

    story = []

    # ── Cover page ───────────────────────────────────────────────────────────
    # Colored background block via a full-width table
    cover_rows = []
    cover_rows.append([Spacer(1, 30)])
    # Logo on cover page (top-center or top-left)
    if logo_path and _logo_placement != "none":
        try:
            logo_w = 80
            cover_rows.append([Image(logo_path, width=logo_w, height=logo_w)])
            cover_rows.append([Spacer(1, 16)])
        except Exception:
            pass
    cover_rows.append([Paragraph(doc_title, COVER_TITLE)])
    cover_rows.append([Spacer(1, 8)])
    cover_rows.append([Paragraph(business_name or "", COVER_SUB)])
    cover_rows.append([Spacer(1, 4)])
    cover_rows.append([Paragraph(datetime.utcnow().strftime("%B %d, %Y"), COVER_DATE)])
    cover_rows.append([Spacer(1, 60)])
    cover_content = cover_rows
    cover_tbl = Table(cover_content, colWidths=[page_w - 4.4 * cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), COVER_BG),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 24),
        ("RIGHTPADDING", (0, 0), (-1, -1), 24),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ]))
    story.append(cover_tbl)
    story.append(PageBreak())

    # inline bold/italic helper
    def _inline(text: str) -> str:
        text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
        text = re.sub(r"`(.*?)`", r"<font name='Courier' size='9'>\1</font>", text)
        return text

    _OL_CTR = 0
    _first_h1 = True
    for kind, raw in blocks:
        if kind == "h1":
            # Skip the first H1 — it's already on the cover page
            if _first_h1:
                _first_h1 = False
                continue
            story.append(Paragraph(_strip(raw), H1))
            story.append(HRFlowable(width="100%", thickness=1.2, color=PRIMARY, spaceAfter=10))
        elif kind == "h2":
            story.append(Paragraph(_inline(_strip(raw)), H2))
            story.append(HRFlowable(width="40%", thickness=2, color=PRIMARY_L, spaceAfter=8))
        elif kind == "h3":
            story.append(Paragraph(_inline(_strip(raw)), H3))
        elif kind == "h4":
            story.append(Paragraph(_inline(_strip(raw)), H4))
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
                # pad short rows
                rows = [r + [""] * (ncols - len(r)) for r in rows]
                # Convert cells to Paragraphs for inline formatting
                para_rows = []
                for i, row in enumerate(rows):
                    para_row = []
                    for cell in row:
                        style = TBL_HEAD_CELL if i == 0 else TBL_CELL
                        para_row.append(Paragraph(_inline(cell), style))
                    para_rows.append(para_row)
                col_w = (A4[0] - 4.4 * cm) / ncols
                tbl = Table(para_rows, colWidths=[col_w] * ncols, repeatRows=1)
                tbl.setStyle(TableStyle([
                    # Header
                    ("BACKGROUND",   (0, 0), (-1, 0),  TABLE_HEAD),
                    ("TEXTCOLOR",    (0, 0), (-1, 0),  INK),
                    ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
                    ("FONTSIZE",     (0, 0), (-1, 0),  10),
                    ("BOTTOMPADDING",(0, 0), (-1, 0),  8),
                    ("TOPPADDING",   (0, 0), (-1, 0),  8),
                    # Body
                    ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE",     (0, 1), (-1, -1), 10),
                    ("ROWBACKGROUNDS",(0, 1),(-1, -1), [colors.white, TABLE_ALT]),
                    ("PADDING",      (0, 1), (-1, -1), 6),
                    # Border
                    ("GRID",         (0, 0), (-1, -1), 0.4, RULE),
                    ("LINEBELOW",    (0, 0), (-1, 0),  1,   PRIMARY_L),
                    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
                ]))
                story.append(tbl)
                story.append(Spacer(1, 10))
        elif kind == "p":
            story.append(Paragraph(_inline(raw), BP))

    # ── Signature block from style profile ───────────────────────────────────
    _sig_name = (s.get("signature_name") or "").strip()
    _sig_title = (s.get("signature_title") or "").strip()
    _sig_contact = (s.get("signature_contact") or "").strip()
    if _sig_name or _sig_title or _sig_contact:
        story.append(Spacer(1, 16))
        story.append(HRFlowable(width="100%", thickness=0.4, color=RULE, spaceAfter=8))
        SIG = _s(name="ZSig", fontSize=10.5, leading=15, textColor=BODY, fontName=_body_font)
        if _sig_name:
            story.append(Paragraph(f"<b>{_sig_name}</b>", SIG))
        if _sig_title:
            story.append(Paragraph(_sig_title, SIG))
        if _sig_contact:
            story.append(Paragraph(_sig_contact, SIG))

    # ── Footer text from style profile ────────────────────────────────────────
    _footer_text = (s.get("footer_text") or "").strip()
    if _footer_text:
        story.append(Spacer(1, 12))
        FTR_CUSTOM = _s(name="ZFtrCustom", fontSize=8.5, leading=12, textColor=MUTED, fontName=_body_font)
        story.append(Paragraph(_footer_text, FTR_CUSTOM))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)

    # Clean up temp logo file
    if logo_path:
        try:
            os.unlink(logo_path)
        except Exception:
            pass

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
