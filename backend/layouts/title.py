"""
layouts/title.py — Cover / Title slide
Primary color background · company name · tagline · footer
"""
from pptx.enum.text import PP_ALIGN
from .base import add_shape, add_text, set_slide_bg, tint, RECT


def render(slide, content: dict, brand: dict, pack: dict) -> None:
    primary = brand["primary"]
    white   = "#FFFFFF"
    font_h  = brand.get("font_header", "Calibri")

    # Full-bleed primary background
    set_slide_bg(slide, primary)

    # Optional: thin accent bar on left (bold pack only)
    if pack.get("accent_placement") == "left_bar":
        accent = brand.get("accent", brand["primary"])
        add_shape(slide, RECT, 0, 0, 0.06, 7.5, color=accent)

    # Company / deck name — large + bold
    name = content.get("name") or brand.get("name", "")
    add_text(slide, name,
             0.7, 1.8, 11.6, 2.2,
             size=pack.get("title_font_size", 38) + 16,
             bold=True,
             color=white,
             align=PP_ALIGN.LEFT,
             font=font_h)

    # Tagline — skip if empty or just repeats the company name
    tagline = content.get("tagline") or brand.get("tagline", "")
    if tagline and tagline.strip().lower() != name.strip().lower():
        tag_color = _hex_tint(primary, 0.72)
        add_text(slide, tagline,
                 0.7, 4.2, 9.5, 0.9,
                 size=pack.get("body_font_size", 14) + 8,
                 color=tag_color,
                 align=PP_ALIGN.LEFT,
                 font=brand.get("font_body", "Calibri"))

    # Footer: website · founder
    parts = [x for x in [content.get("website", ""), content.get("founder", "")] if x]
    if parts:
        footer_color = _hex_tint(primary, 0.55)
        add_text(slide, "   ·   ".join(parts),
                 0.7, 6.75, 11.6, 0.45,
                 size=12,
                 color=footer_color,
                 align=PP_ALIGN.LEFT,
                 font=brand.get("font_body", "Calibri"))


def _hex_tint(hex_str: str, blend: float) -> str:
    """Return a lightened hex string for text on primary bg."""
    from .base import tint, hex_to_rgb
    rgb = tint(hex_str, blend)
    return f"#{str(rgb)}"
