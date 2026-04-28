import asyncio
import base64
import os
import tempfile
import uuid
from typing import List, Dict, Any, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Temp directory for PPTX files
TEMP_DIR = tempfile.gettempdir()


def _hex_to_rgb(hex_color: str, fallback: tuple = (79, 70, 229)) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = (hex_color or "").strip()
    if hex_color.startswith("#"):
        hex_color = hex_color[1:]
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    try:
        return int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    except Exception:
        return fallback


def _resolve_font(font_style: str) -> str:
    """Return font name based on style profile."""
    s = (font_style or "").lower()
    if s in ("serif", "classic"):
        return "Times New Roman"
    if s == "modern":
        return "Arial"
    if s == "minimal":
        return "Calibri"
    return "Arial"  # default


def generate_presentation(
    title: str,
    slides_data: List[Dict[str, Any]],
    business_name: str = "My Business",
    style: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generates a branded PowerPoint presentation (.pptx) and returns the file path.

    slides_data format:
    [
        {"title": "Slide 1 Title", "content": ["Point 1", "Point 2"]},
        {"title": "Slide 2 Title", "content": ["Point A", "Point B"]}
    ]
    """
    style = style or {}

    # Brand colors
    primary_rgb = _hex_to_rgb(style.get("primary_color", ""), (79, 70, 229))
    secondary_rgb = _hex_to_rgb(style.get("secondary_color", ""), (238, 242, 255))
    ink_rgb = (17, 24, 39)
    body_rgb = (55, 65, 81)

    # Brand font
    font_name = _resolve_font(style.get("font_style", ""))

    try:
        prs = Presentation()

        # ── Slide 1: Branded Title Slide ───────────────────────────────────────
        blank_layout = prs.slide_layouts[6]  # blank
        title_slide = prs.slides.add_slide(blank_layout)

        # Background with brand color
        background = title_slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*primary_rgb)

        # Title text box
        left = Inches(0.5)
        top = Inches(2.5)
        width = Inches(9)
        height = Inches(1.5)
        title_box = title_slide.shapes.add_textbox(left, top, width, height)
        title_frame = title_box.text_frame
        title_frame.text = title
        title_para = title_frame.paragraphs[0]
        title_para.alignment = PP_ALIGN.CENTER
        title_para.font.size = Pt(44)
        title_para.font.bold = True
        title_para.font.color.rgb = RGBColor(255, 255, 255)
        title_para.font.name = font_name

        # Subtitle / business name
        subtitle_box = title_slide.shapes.add_textbox(left, top + Inches(1.6), width, Inches(0.8))
        subtitle_frame = subtitle_box.text_frame
        subtitle_frame.text = f"Presented by {business_name}"
        subtitle_para = subtitle_frame.paragraphs[0]
        subtitle_para.alignment = PP_ALIGN.CENTER
        subtitle_para.font.size = Pt(20)
        subtitle_para.font.color.rgb = RGBColor(255, 255, 255)
        subtitle_para.font.name = font_name

        # ── Content Slides ───────────────────────────────────────────────────────
        for slide_data in slides_data:
            slide = prs.slides.add_slide(blank_layout)

            # Light background
            bg = slide.background
            bg_fill = bg.fill
            bg_fill.solid()
            bg_fill.fore_color.rgb = RGBColor(255, 255, 255)

            # Title bar with brand color
            title_bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(10), Inches(1.2))  # rectangle
            title_bar.fill.solid()
            title_bar.fill.fore_color.rgb = RGBColor(*primary_rgb)
            title_bar.line.fill.background()

            # Title text
            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.2), Inches(9), Inches(0.8))
            title_frame = title_box.text_frame
            title_frame.text = slide_data.get("title", "Slide")
            title_para = title_frame.paragraphs[0]
            title_para.font.size = Pt(28)
            title_para.font.bold = True
            title_para.font.color.rgb = RGBColor(255, 255, 255)
            title_para.font.name = font_name

            # Content bullets
            content_items = slide_data.get("content", [])
            bullet_left = Inches(0.8)
            bullet_top = Inches(1.6)
            bullet_width = Inches(8.4)

            for i, point in enumerate(content_items):
                bullet_box = slide.shapes.add_textbox(bullet_left, bullet_top, bullet_width, Inches(0.6))
                bullet_frame = bullet_box.text_frame
                bullet_frame.text = f"• {point}"
                bullet_para = bullet_frame.paragraphs[0]
                bullet_para.font.size = Pt(20)
                bullet_para.font.color.rgb = RGBColor(*body_rgb)
                bullet_para.font.name = font_name
                bullet_top += Inches(0.7)

        # Save to temp file
        filename = f"presentation_{uuid.uuid4().hex[:8]}.pptx"
        filepath = os.path.join(TEMP_DIR, filename)
        prs.save(filepath)

        return {
            "success": True,
            "filename": filename,
            "filepath": filepath,
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
) -> Dict[str, Any]:
    """
    Generate presentation and upload to S3. Returns S3 URL.
    """
    result = generate_presentation(title, slides_data, business_name, style)
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
        "url": file_url,
        "filename": result.get("filename"),
    }
