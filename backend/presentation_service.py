import asyncio
import base64
import os
import uuid
from typing import List, Dict, Any, Optional
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image, ImageDraw, ImageFont

PRESENTATIONS_DIR = os.path.join(os.getcwd(), "public", "presentations")
os.makedirs(PRESENTATIONS_DIR, exist_ok=True)

# ── Color Themes ──────────────────────────────────────────────────────────
THEMES = {
    "dark": {
        "bg": RGBColor(0x0B, 0x1D, 0x14),          # deep forest
        "bg_accent": RGBColor(0x07, 0x1A, 0x10),    # darker green
        "accent": RGBColor(0x4C, 0xD1, 0x37),       # brand green
        "accent2": RGBColor(0x00, 0x9B, 0x3A),      # darker brand
        "title": RGBColor(0xFF, 0xFF, 0xFF),
        "subtitle": RGBColor(0xB0, 0xE0, 0xC0),
        "body": RGBColor(0xD0, 0xE8, 0xD8),
        "light": RGBColor(0xE8, 0xF5, 0xE9),
        "divider": RGBColor(0x4C, 0xD1, 0x37),
    },
    "light": {
        "bg": RGBColor(0xFF, 0xFF, 0xFF),
        "bg_accent": RGBColor(0xF0, 0xFD, 0xF4),
        "accent": RGBColor(0x00, 0x9B, 0x3A),
        "accent2": RGBColor(0x00, 0x7A, 0x2E),
        "title": RGBColor(0x0A, 0x26, 0x14),
        "subtitle": RGBColor(0x3A, 0x6B, 0x4A),
        "body": RGBColor(0x33, 0x33, 0x33),
        "light": RGBColor(0xF0, 0xFD, 0xF4),
        "divider": RGBColor(0x00, 0x9B, 0x3A),
    },
    "navy": {
        "bg": RGBColor(0x0F, 0x17, 0x2A),
        "bg_accent": RGBColor(0x14, 0x1E, 0x33),
        "accent": RGBColor(0x38, 0x9C, 0xE6),
        "accent2": RGBColor(0x21, 0x6F, 0xDB),
        "title": RGBColor(0xFF, 0xFF, 0xFF),
        "subtitle": RGBColor(0xA0, 0xC4, 0xE8),
        "body": RGBColor(0xC8, 0xD8, 0xE8),
        "light": RGBColor(0xE0, 0xEE, 0xF8),
        "divider": RGBColor(0x38, 0x9C, 0xE6),
    },
    "warm": {
        "bg": RGBColor(0x1A, 0x12, 0x0B),
        "bg_accent": RGBColor(0x22, 0x18, 0x10),
        "accent": RGBColor(0xF5, 0x9E, 0x0B),
        "accent2": RGBColor(0xD9, 0x77, 0x06),
        "title": RGBColor(0xFF, 0xFF, 0xFF),
        "subtitle": RGBColor(0xFD, 0xD8, 0xA8),
        "body": RGBColor(0xE0, 0xD0, 0xC0),
        "light": RGBColor(0xFF, 0xF7, 0xED),
        "divider": RGBColor(0xF5, 0x9E, 0x0B),
    },
}

DEFAULT_THEME = "dark"


def _lighten(color: RGBColor, amount: int = 40) -> RGBColor:
    """Return a lighter version of an RGBColor by adding `amount` to each channel."""
    hex_str = str(color)  # e.g. "009B3A"
    r = min(255, int(hex_str[0:2], 16) + amount)
    g = min(255, int(hex_str[2:4], 16) + amount)
    b = min(255, int(hex_str[4:6], 16) + amount)
    return RGBColor(r, g, b)


# ── Helpers ────────────────────────────────────────────────────────────────

def _add_bg(slide, color: RGBColor):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_rect(slide, left, top, width, height, fill_color: RGBColor, line_color=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    return shape


def _add_textbox(slide, left, top, width, height, text: str, font_size=18,
                 color: RGBColor = RGBColor(0xFF, 0xFF, 0xFF), bold=False,
                 alignment=PP_ALIGN.LEFT, font_name="Calibri"):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font_name
    p.alignment = alignment
    return txBox


def _add_bullet_textbox(slide, left, top, width, height, items: List[str],
                        font_size=16, color: RGBColor = RGBColor(0xFF, 0xFF, 0xFF),
                        bullet_char="●", spacing=Pt(8), font_name="Calibri"):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = f"  {bullet_char}  {item}"
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.font.name = font_name
        p.space_after = spacing
    return txBox


# ── Slide Layouts ──────────────────────────────────────────────────────────

def _slide_title(prs, theme, title: str, subtitle: str):
    """Full-bleed title slide with accent bar and decorative circle."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    _add_bg(slide, theme["bg"])

    # Left accent bar
    _add_rect(slide, Inches(0), Inches(0), Inches(0.12), Inches(7.5), theme["accent"])

    # Decorative circle (top-right)
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8.2), Inches(-0.6), Inches(2.8), Inches(2.8))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _lighten(theme["accent2"], 40)
    shape.line.fill.background()

    # Small decorative circle bottom-left
    shape2 = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(-0.4), Inches(5.8), Inches(1.6), Inches(1.6))
    shape2.fill.solid()
    shape2.fill.fore_color.rgb = _lighten(theme["accent2"], 30)
    shape2.line.fill.background()

    # Title
    _add_textbox(slide, Inches(0.8), Inches(2.0), Inches(8), Inches(1.5),
                 title, font_size=40, color=theme["title"], bold=True, font_name="Calibri Light")

    # Subtitle
    _add_textbox(slide, Inches(0.8), Inches(3.6), Inches(7), Inches(0.8),
                 subtitle, font_size=20, color=theme["subtitle"], font_name="Calibri")

    # Bottom accent line
    _add_rect(slide, Inches(0.8), Inches(4.6), Inches(2.5), Inches(0.06), theme["accent"])


def _slide_section(prs, theme, title: str):
    """Section divider slide — centered title on accent background panel."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Center panel
    _add_rect(slide, Inches(1.2), Inches(2.0), Inches(7.6), Inches(3.5), theme["bg_accent"])

    # Top accent line on panel
    _add_rect(slide, Inches(1.2), Inches(2.0), Inches(7.6), Inches(0.08), theme["accent"])

    # Title centered
    _add_textbox(slide, Inches(1.5), Inches(2.8), Inches(7), Inches(2.0),
                 title, font_size=36, color=theme["title"], bold=True,
                 alignment=PP_ALIGN.CENTER, font_name="Calibri Light")


def _slide_content(prs, theme, title: str, content: List[str]):
    """Standard content slide — title top-left with accent underline, bullets below."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Top accent bar (full width)
    _add_rect(slide, Inches(0), Inches(0), Inches(10), Inches(0.06), theme["accent"])

    # Title
    _add_textbox(slide, Inches(0.7), Inches(0.4), Inches(8.5), Inches(0.8),
                 title, font_size=28, color=theme["title"], bold=True, font_name="Calibri Light")

    # Accent underline
    _add_rect(slide, Inches(0.7), Inches(1.2), Inches(1.8), Inches(0.05), theme["accent"])

    # Bullets
    _add_bullet_textbox(slide, Inches(0.7), Inches(1.6), Inches(8.5), Inches(5.0),
                        content, font_size=18, color=theme["body"], bullet_char="▸",
                        spacing=Pt(10), font_name="Calibri")

    # Page number area (bottom right subtle)
    _add_textbox(slide, Inches(8.8), Inches(6.9), Inches(1), Inches(0.4),
                 "", font_size=10, color=theme["subtitle"])


def _slide_two_column(prs, theme, title: str, left_items: List[str], right_items: List[str],
                      left_header: str = "", right_header: str = ""):
    """Two-column content slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Top accent bar
    _add_rect(slide, Inches(0), Inches(0), Inches(10), Inches(0.06), theme["accent"])

    # Title
    _add_textbox(slide, Inches(0.7), Inches(0.4), Inches(8.5), Inches(0.8),
                 title, font_size=28, color=theme["title"], bold=True, font_name="Calibri Light")

    # Accent underline
    _add_rect(slide, Inches(0.7), Inches(1.2), Inches(1.8), Inches(0.05), theme["accent"])

    # Left column background
    _add_rect(slide, Inches(0.5), Inches(1.6), Inches(4.3), Inches(5.0), theme["bg_accent"])

    # Right column background
    _add_rect(slide, Inches(5.2), Inches(1.6), Inches(4.3), Inches(5.0), theme["bg_accent"])

    # Left header
    y = Inches(1.8)
    if left_header:
        _add_textbox(slide, Inches(0.7), y, Inches(3.9), Inches(0.5),
                     left_header, font_size=16, color=theme["accent"], bold=True)
        y = Inches(2.4)

    _add_bullet_textbox(slide, Inches(0.7), y, Inches(3.9), Inches(4.0),
                        left_items, font_size=15, color=theme["body"], bullet_char="▸",
                        spacing=Pt(8))

    # Right header
    y = Inches(1.8)
    if right_header:
        _add_textbox(slide, Inches(5.4), y, Inches(3.9), Inches(0.5),
                     right_header, font_size=16, color=theme["accent"], bold=True)
        y = Inches(2.4)

    _add_bullet_textbox(slide, Inches(5.4), y, Inches(3.9), Inches(4.0),
                        right_items, font_size=15, color=theme["body"], bullet_char="▸",
                        spacing=Pt(8))

    # Vertical divider line
    _add_rect(slide, Inches(4.95), Inches(1.8), Inches(0.03), Inches(4.5), theme["divider"])


def _slide_quote(prs, theme, quote: str, attribution: str = ""):
    """Quote / highlight slide — large centered text."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Large accent quote mark
    _add_textbox(slide, Inches(0.5), Inches(1.0), Inches(2), Inches(2),
                 "❝", font_size=72, color=theme["accent"], bold=True,
                 alignment=PP_ALIGN.LEFT, font_name="Georgia")

    # Quote text
    _add_textbox(slide, Inches(1.2), Inches(2.2), Inches(7.5), Inches(2.5),
                 quote, font_size=26, color=theme["title"], bold=False,
                 alignment=PP_ALIGN.LEFT, font_name="Georgia")

    # Attribution
    if attribution:
        _add_textbox(slide, Inches(1.2), Inches(4.8), Inches(7.5), Inches(0.6),
                     f"— {attribution}", font_size=16, color=theme["subtitle"],
                     alignment=PP_ALIGN.LEFT, font_name="Calibri")

    # Bottom accent bar
    _add_rect(slide, Inches(1.2), Inches(5.6), Inches(3), Inches(0.05), theme["accent"])


def _slide_image_text(prs, theme, title: str, content: List[str], image_url: Optional[str] = None):
    """Content slide with image placeholder on right, text on left."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Top accent bar
    _add_rect(slide, Inches(0), Inches(0), Inches(10), Inches(0.06), theme["accent"])

    # Title
    _add_textbox(slide, Inches(0.7), Inches(0.4), Inches(8.5), Inches(0.8),
                 title, font_size=28, color=theme["title"], bold=True, font_name="Calibri Light")

    # Accent underline
    _add_rect(slide, Inches(0.7), Inches(1.2), Inches(1.8), Inches(0.05), theme["accent"])

    # Left text
    _add_bullet_textbox(slide, Inches(0.7), Inches(1.6), Inches(4.8), Inches(5.0),
                        content, font_size=17, color=theme["body"], bullet_char="▸",
                        spacing=Pt(10))

    # Right image area — placeholder box
    _add_rect(slide, Inches(5.8), Inches(1.4), Inches(3.8), Inches(4.5), theme["bg_accent"],
              line_color=theme["divider"])

    # Image placeholder text
    _add_textbox(slide, Inches(5.8), Inches(3.2), Inches(3.8), Inches(0.8),
                 "📷  Image", font_size=16, color=theme["subtitle"],
                 alignment=PP_ALIGN.CENTER)

    # Try to add actual image if URL provided
    if image_url:
        try:
            slide.shapes.add_picture(image_url, Inches(5.9), Inches(1.5), Inches(3.6), Inches(4.3))
        except Exception:
            pass  # keep placeholder


def _slide_key_points(prs, theme, title: str, points: List[Dict[str, str]]):
    """Key points / icon grid slide — up to 4 points with title + description each."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Top accent bar
    _add_rect(slide, Inches(0), Inches(0), Inches(10), Inches(0.06), theme["accent"])

    # Title
    _add_textbox(slide, Inches(0.7), Inches(0.4), Inches(8.5), Inches(0.8),
                 title, font_size=28, color=theme["title"], bold=True, font_name="Calibri Light")

    # Accent underline
    _add_rect(slide, Inches(0.7), Inches(1.2), Inches(1.8), Inches(0.05), theme["accent"])

    # Cards grid (2x2 max)
    positions = [
        (Inches(0.5), Inches(1.6)),
        (Inches(5.2), Inches(1.6)),
        (Inches(0.5), Inches(4.2)),
        (Inches(5.2), Inches(4.2)),
    ]
    card_w = Inches(4.3)
    card_h = Inches(2.2)

    for i, point in enumerate(points[:4]):
        px, py = positions[i]
        # Card background
        _add_rect(slide, px, py, card_w, card_h, theme["bg_accent"])
        # Card left accent
        _add_rect(slide, px, py, Inches(0.08), card_h, theme["accent"])
        # Point title
        pt_title = point.get("title", point.get("header", ""))
        pt_desc = point.get("description", point.get("body", point.get("content", "")))
        if pt_title:
            _add_textbox(slide, px + Inches(0.3), py + Inches(0.2), card_w - Inches(0.5), Inches(0.5),
                         pt_title, font_size=18, color=theme["accent"], bold=True)
        if pt_desc:
            _add_textbox(slide, px + Inches(0.3), py + Inches(0.8), card_w - Inches(0.5), Inches(1.2),
                         pt_desc, font_size=14, color=theme["body"])


def _slide_ending(prs, theme, business_name: str, tagline: str = ""):
    """Thank-you / closing slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, theme["bg"])

    # Decorative circle top-right
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(7.5), Inches(-1), Inches(4), Inches(4))
    shape.fill.solid()
    shape.fill.fore_color.rgb = _lighten(theme["accent2"], 30)
    shape.line.fill.background()

    # Left accent bar
    _add_rect(slide, Inches(0), Inches(0), Inches(0.12), Inches(7.5), theme["accent"])

    # Thank you
    _add_textbox(slide, Inches(0.8), Inches(2.2), Inches(8), Inches(1.2),
                 "Thank You", font_size=44, color=theme["title"], bold=True,
                 alignment=PP_ALIGN.LEFT, font_name="Calibri Light")

    # Accent line
    _add_rect(slide, Inches(0.8), Inches(3.5), Inches(2.5), Inches(0.06), theme["accent"])

    # Business name
    _add_textbox(slide, Inches(0.8), Inches(3.9), Inches(7), Inches(0.7),
                 business_name, font_size=22, color=theme["subtitle"],
                 font_name="Calibri")

    # Tagline
    if tagline:
        _add_textbox(slide, Inches(0.8), Inches(4.7), Inches(7), Inches(0.6),
                     tagline, font_size=16, color=theme["body"], font_name="Calibri")


# ── Thumbnail Generator ──────────────────────────────────────────────────────

def _rgb_tuple(color: RGBColor) -> tuple:
    """Convert RGBColor to (r, g, b) tuple for Pillow."""
    h = str(color)  # e.g. "0B1D14"
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _generate_thumbnail(prs, theme, title: str, business_name: str, thumb_path: str):
    """Generate a PNG thumbnail that mimics the title slide layout."""
    W, H = 1280, 720  # 16:9 preview
    bg = _rgb_tuple(theme["bg"])
    accent = _rgb_tuple(theme["accent"])
    accent2 = _rgb_tuple(theme["accent2"])
    title_col = _rgb_tuple(theme["title"])
    subtitle_col = _rgb_tuple(theme["subtitle"])

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Left accent bar
    draw.rectangle([0, 0, 12, H], fill=accent)

    # Decorative circle top-right (lighter accent2)
    lighter = tuple(min(255, c + 40) for c in accent2)
    draw.ellipse([W - 280, -80, W + 200, 400], fill=lighter)

    # Small decorative circle bottom-left
    lighter2 = tuple(min(255, c + 30) for c in accent2)
    draw.ellipse([-60, H - 180, 140, H + 40], fill=lighter2)

    # Bottom accent line
    draw.rectangle([80, H - 160, 330, H - 154], fill=accent)

    # Title text
    try:
        font_title = ImageFont.truetype("calibril.ttf", 56)
    except Exception:
        font_title = ImageFont.truetype("arial.ttf", 56) if os.name == "nt" else ImageFont.load_default()
    try:
        font_sub = ImageFont.truetype("calibri.ttf", 28)
    except Exception:
        font_sub = ImageFont.truetype("arial.ttf", 28) if os.name == "nt" else ImageFont.load_default()

    # Wrap title if too long
    draw.text((100, 260), title, fill=title_col, font=font_title)
    draw.text((100, 380), f"Presented by {business_name}", fill=subtitle_col, font=font_sub)

    # Slide count badge bottom-right
    slide_count = len(prs.slides)
    badge_text = f"{slide_count} slides"
    try:
        font_badge = ImageFont.truetype("calibri.ttf", 18)
    except Exception:
        font_badge = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    bx, by = W - tw - 40, H - th - 20
    draw.rounded_rectangle([bx - 12, by - 8, bx + tw + 12, by + th + 8], radius=8, fill=accent)
    draw.text((bx, by), badge_text, fill=(255, 255, 255), font=font_badge)

    img.save(thumb_path, "PNG")


# ── Layout Router ──────────────────────────────────────────────────────────

LAYOUT_MAP = {
    "title": _slide_title,
    "section": _slide_section,
    "content": _slide_content,
    "two_column": _slide_two_column,
    "quote": _slide_quote,
    "image_text": _slide_image_text,
    "key_points": _slide_key_points,
    "ending": _slide_ending,
}


def generate_presentation(
    title: str,
    slides_data: List[Dict[str, Any]],
    business_name: str = "My Business",
    theme_name: str = DEFAULT_THEME,
    tagline: str = "",
) -> Dict[str, Any]:
    """
    Generates a professional PowerPoint presentation (.pptx).

    slides_data format — each slide object:
      Common keys:
        - layout (str): "title" | "section" | "content" | "two_column" |
                        "quote" | "image_text" | "key_points" | "ending"
                        Default: "content" (first slide auto-gets "title")

      Layout-specific keys:
        title:   title, subtitle
        section: title
        content: title, content (list of str)
        two_column: title, left_items, right_items, left_header?, right_header?
        quote:   quote, attribution?
        image_text: title, content (list of str), image_url?
        key_points: title, points (list of {title, description})
        ending:  (uses business_name + tagline — no extra keys needed)
    """
    try:
        theme = THEMES.get(theme_name, THEMES[DEFAULT_THEME])
        prs = Presentation()
        prs.slide_width = Inches(10)
        prs.slide_height = Inches(7.5)

        for idx, sd in enumerate(slides_data):
            layout = sd.get("layout", "content").lower()

            # Auto-make first slide a title slide if not specified
            if idx == 0 and layout not in ("title", "section", "ending"):
                layout = "title"

            # Auto-add ending slide if last slide isn't already one
            if idx == len(slides_data) - 1 and layout not in ("ending", "title"):
                # First render the current slide
                _render_slide(prs, theme, layout, sd, business_name, tagline)
                # Then append ending
                _slide_ending(prs, theme, business_name, tagline)
                continue

            _render_slide(prs, theme, layout, sd, business_name, tagline)

        # If no slides at all, add title + ending
        if not slides_data:
            _slide_title(prs, theme, title, f"Presented by {business_name}")
            _slide_ending(prs, theme, business_name, tagline)

        filename = f"presentation_{uuid.uuid4().hex[:8]}.pptx"
        filepath = os.path.join(PRESENTATIONS_DIR, filename)
        prs.save(filepath)

        download_url = f"/api/media/presentations/{filename}"

        # Generate PNG thumbnail preview of the title slide
        thumb_filename = f"preview_{uuid.uuid4().hex[:8]}.png"
        thumb_path = os.path.join(PRESENTATIONS_DIR, thumb_filename)
        thumb_url = f"/api/media/presentations/{thumb_filename}"
        _generate_thumbnail(prs, theme, title, business_name, thumb_path)

        return {
            "success": True,
            "filename": filename,
            "filepath": filepath,
            "url": download_url,
            "thumbnail_url": thumb_url,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


async def generate_presentation_with_upload(
    title: str,
    slides_data: List[Dict[str, Any]],
    business_name: str = "My Business",
    style: Optional[Dict[str, Any]] = None,
    theme_name: str = DEFAULT_THEME,
    tagline: str = "",
) -> Dict[str, Any]:
    """Generate presentation and upload to S3. Returns S3 URL."""
    result = generate_presentation(title, slides_data, business_name, theme_name=theme_name, tagline=tagline)
    if result.get("error"):
        return result

    filepath = result["filepath"]
    file_url = None

    try:
        from pathlib import Path
        from image_handler import S3Handler

        file_bytes = Path(filepath).read_bytes()
        b64 = base64.b64encode(file_bytes).decode()
        s3_name = f"pptx-{uuid.uuid4().hex[:8]}.pptx"
        file_url = await S3Handler.upload_file(
            b64, s3_name, content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
    except Exception as e:
        import logging
        logging.warning("[presentation_service] S3 upload failed: %s", e)
    finally:
        try:
            os.unlink(filepath)
        except Exception:
            pass

    return {
        "success": True,
        "url": file_url or result.get("url"),
        "thumbnail_url": result.get("thumbnail_url"),
        "filename": result.get("filename"),
    }


def _render_slide(prs, theme, layout: str, sd: Dict[str, Any], business_name: str, tagline: str):
    if layout == "title":
        _slide_title(prs, theme,
                     sd.get("title", "Presentation"),
                     sd.get("subtitle", f"Presented by {business_name}"))
    elif layout == "section":
        _slide_section(prs, theme, sd.get("title", "Section"))
    elif layout == "two_column":
        _slide_two_column(prs, theme,
                          sd.get("title", ""),
                          sd.get("left_items", sd.get("left", [])),
                          sd.get("right_items", sd.get("right", [])),
                          sd.get("left_header", ""),
                          sd.get("right_header", ""))
    elif layout == "quote":
        _slide_quote(prs, theme,
                     sd.get("quote", sd.get("content", "")),
                     sd.get("attribution", ""))
    elif layout == "image_text":
        _slide_image_text(prs, theme,
                          sd.get("title", ""),
                          sd.get("content", []),
                          sd.get("image_url"))
    elif layout == "key_points":
        _slide_key_points(prs, theme,
                          sd.get("title", ""),
                          sd.get("points", []))
    elif layout == "ending":
        _slide_ending(prs, theme, business_name, tagline)
    else:
        # Default: content
        _slide_content(prs, theme,
                       sd.get("title", "Slide"),
                       sd.get("content", []))
