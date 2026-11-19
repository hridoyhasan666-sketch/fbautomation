"""
Story Card Image Renderer.
Generates 1080x1350 portrait cards (4:5 aspect ratio) for Facebook feed.
Supports vintage newsprint styling, newspaper clippings, typography, price badges, and date masking.
"""

import os
import requests
from io import BytesIO
from typing import Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from utils.config import CONFIG
from utils.cpi import calculate_inflation

SERIF_FONT_PATH = "C:/Windows/Fonts/georgia.ttf"
BOLD_SERIF_FONT_PATH = "C:/Windows/Fonts/georgiab.ttf"
FALLBACK_FONT_PATH = "C:/Windows/Fonts/times.ttf"

def get_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.truetype(FALLBACK_FONT_PATH, size)
        except Exception:
            return ImageFont.load_default()

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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_dir = output_dir or os.path.join(base_dir, "data", "rendered_cards")
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_or_create_background(self, image_url: str, width: int = 1080, height: int = 1350) -> Image.Image:
        """Downloads clipping image if available and darkens/blurs it, or creates vintage newsprint."""
        if image_url:
            try:
                resp = requests.get(image_url, timeout=8)
                if resp.status_code == 200:
                    bg = Image.open(BytesIO(resp.content)).convert("RGB")
                    bg = bg.resize((width, height), Image.Resampling.LANCZOS)
                    # Blur and darken
                    bg = bg.filter(ImageFilter.GaussianBlur(radius=8))
                    enhancer = ImageEnhance.Brightness(bg)
                    return enhancer.enhance(0.25) # Darkened
            except Exception as e:
                print(f"[Renderer] Background download failed: {e}")

        # Default vintage dark archive paper background
        bg = Image.new("RGB", (width, height), color=(24, 23, 22))
        draw = ImageDraw.Draw(bg)
        
        # Subtle vintage frame border
        draw.rectangle([(30, 30), (width - 30, height - 30)], outline=(60, 56, 52), width=2)
        draw.rectangle([(38, 38), (width - 38, height - 38)], outline=(110, 102, 92), width=1)
        return bg

    def render_card(self, post_data: Dict[str, Any], seed_card: Dict[str, Any], post_id: str) -> str:
        """
        Renders 1080x1350 card and returns the output file path.
        """
        width, height = 1080, 1350
        image_url = seed_card.get("page_image_url", "")
        img = self.fetch_or_create_background(image_url, width, height)
        draw = ImageDraw.Draw(img)

        fmt = post_data.get("format", "true_retelling")
        place = seed_card.get("place", "Archive Record").upper()
        date_str = str(seed_card.get("date", "1900")).split("-")[0]
        
        # 1. Header Stamp
        stamp_font = get_font(BOLD_SERIF_FONT_PATH, 28)
        if fmt == "guess_year":
            header_text = f"{place} · [YEAR HIDDEN]"
        else:
            header_text = f"{place} · {date_str}"
            
        draw.text((80, 100), header_text, font=stamp_font, fill=(210, 185, 140))
        draw.line([(80, 145), (1000, 145)], fill=(120, 105, 80), width=2)

        # 2. Main Card Text
        card_text = post_data.get("card_text") or post_data.get("selected_hook", "")
        body_font = get_font(SERIF_FONT_PATH, 54)
        
        wrapped_lines = wrap_text(f'"{card_text}"', body_font, max_width=880, draw=draw)
        
        # Calculate vertical position
        line_height = 72
        total_text_height = len(wrapped_lines) * line_height
        start_y = 380 - (total_text_height // 4)

        for i, line in enumerate(wrapped_lines):
            y = start_y + (i * line_height)
            draw.text((80, y), line, font=body_font, fill=(245, 240, 230))

        # 3. Format-specific badges
        if fmt == "price" and seed_card.get("price_data"):
            p_data = seed_card["price_data"]
            cents = p_data.get("price_cents", 100)
            year = p_data.get("year", 1904)
            item = p_data.get("item", "item")
            today_dollars, mult = calculate_inflation(cents / 100.0, year)
            past_val = f"{cents}¢" if cents < 100 else f"${cents/100:.2f}"
            
            badge_y = start_y + total_text_height + 80
            draw.rectangle([(80, badge_y), (1000, badge_y + 160)], fill=(38, 35, 30), outline=(190, 150, 90), width=3)
            
            b_font = get_font(BOLD_SERIF_FONT_PATH, 38)
            badge_line1 = f"{year}: {past_val}  →  TODAY: ${today_dollars:,.2f}"
            badge_line2 = f"({mult}x modern equivalent for {item})"
            
            draw.text((120, badge_y + 30), badge_line1, font=b_font, fill=(255, 215, 120))
            draw.text((120, badge_y + 90), badge_line2, font=get_font(SERIF_FONT_PATH, 28), fill=(200, 195, 185))

        elif fmt == "guess_year":
            badge_y = start_y + total_text_height + 80
            draw.rectangle([(80, badge_y), (1000, badge_y + 130)], fill=(35, 40, 48), outline=(140, 160, 190), width=2)
            b_font = get_font(BOLD_SERIF_FONT_PATH, 34)
            draw.text((120, badge_y + 40), "CAN YOU GUESS THE YEAR? (Drop answer below)", font=b_font, fill=(210, 230, 255))

        # 4. Footer Branding
        draw.line([(80, 1220), (1000, 1220)], fill=(120, 105, 80), width=1)
        footer_font = get_font(SERIF_FONT_PATH, 24)
        draw.text((80, 1245), "OLD NEWS, MODERN LIFE · ARCHIVE DISCOVERY", font=footer_font, fill=(160, 145, 125))

        output_path = os.path.join(self.output_dir, f"card_{post_id}.png")
        img.save(output_path, "PNG", quality=95)
        print(f"[Renderer] Saved story card to: {output_path}")
        return output_path
