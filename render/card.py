"""
Story Card Image Renderer.
Generates 1080x1350 portrait cards (4:5 aspect ratio) for Facebook feed.
Supports vintage newsprint styling, newspaper clippings, typography, price badges, and date masking.
"""

import os
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from utils.config import CONFIG

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Windows fonts locally, DejaVu/Liberation on GitHub's Ubuntu runners.
SERIF_FONTS = [
    "C:/Windows/Fonts/georgia.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "C:/Windows/Fonts/times.ttf",
]
BOLD_SERIF_FONTS = [
    "C:/Windows/Fonts/georgiab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
]

FORMAT_KICKERS = {
    "then_vs_now": "THEN  &  NOW",
    "forgotten_habit": "A FORGOTTEN HABIT",
    "old_wisdom": "OLD WISDOM",
    "life_question": "WHAT WOULD YOU CHOOSE?",
    "short_story": "A SHORT STORY",
}

def get_font(paths: list, size: int):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default(size=size)

def resolve_path(path: str) -> str:
    """Card paths are stored relative to the repo so they work locally and on GitHub Actions."""
    if not path:
        return ""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)

def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """Wraps text so lines fit within max_width."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
                
    if current_line:
        lines.append(" ".join(current_line))
    return lines

class CardRenderer:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(BASE_DIR, "data", "rendered_cards")
        os.makedirs(self.output_dir, exist_ok=True)

    def render_card(self, post_data: Dict[str, Any], post_id: str) -> str:
        """Renders a 1080x1350 card and returns its repo-relative path."""
        width, height = 1080, 1350
        img = Image.new("RGB", (width, height), color=(24, 23, 22))
        draw = ImageDraw.Draw(img)
        draw.rectangle([(30, 30), (width - 30, height - 30)], outline=(60, 56, 52), width=2)
        draw.rectangle([(38, 38), (width - 38, height - 38)], outline=(110, 102, 92), width=1)

        fmt = post_data.get("format", "")
        brand = CONFIG.get("brand", {})

        # 1. Kicker
        kicker = FORMAT_KICKERS.get(fmt, brand.get("tagline", "").upper())
        draw.text((80, 100), kicker, font=get_font(BOLD_SERIF_FONTS, 30), fill=(210, 185, 140))
        draw.line([(80, 150), (1000, 150)], fill=(120, 105, 80), width=2)

        # 2. Main text, shrunk until it fits
        card_text = post_data.get("card_text") or post_data.get("selected_hook", "")
        for size in (64, 58, 52, 46, 40):
            font = get_font(SERIF_FONTS, size)
            lines = wrap_text(card_text, font, max_width=900, draw=draw)
            line_h = int(size * 1.35)
            if len(lines) * line_h <= 900:
                break
        total_h = len(lines) * line_h
        start_y = 185 + (1035 - total_h) // 2
        for i, line in enumerate(lines):
            draw.text((80, start_y + i * line_h), line, font=font, fill=(245, 240, 230))

        # 3. Footer
        draw.line([(80, 1220), (1000, 1220)], fill=(120, 105, 80), width=1)
        footer = f"{brand.get('page_name', '')}  ·  {brand.get('tagline', '')}".upper()
        draw.text((80, 1245), footer, font=get_font(SERIF_FONTS, 24), fill=(160, 145, 125))

        filename = f"card_{post_id}.png"
        img.save(os.path.join(self.output_dir, filename), "PNG")
        rel = os.path.relpath(os.path.join(self.output_dir, filename), BASE_DIR).replace(os.sep, "/")
        print(f"[Renderer] Saved card: {rel}")
        return rel
