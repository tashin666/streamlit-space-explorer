from io import BytesIO
from typing import Dict, Optional

from PIL import Image, ImageDraw, ImageFont
import qrcode
import requests

DEFAULT_W, DEFAULT_H = 1200, 630  # social share friendly

def fetch_image_bytes(url: str) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.content
    except Exception:
        return None

def build_share_card(item: Dict, permalink: str) -> BytesIO:
    """
    Create a PNG share card with the APOD image (or thumbnail),
    title/date/caption overlay, and a QR to the permalink.
    """
    bg = Image.new("RGB", (DEFAULT_W, DEFAULT_H), (10, 15, 26))
    draw = ImageDraw.Draw(bg)

    # Load image
    img_bytes = None
    url = item.get("hdurl") or item.get("url") or item.get("thumbnail_url")
    if url:
        img_bytes = fetch_image_bytes(url)
    if img_bytes:
        src = Image.open(BytesIO(img_bytes)).convert("RGB")
        # Fit center-crop
        src_ratio = src.width / src.height
        bg_ratio = DEFAULT_W / DEFAULT_H
        if src_ratio > bg_ratio:  # source too wide
            new_h = DEFAULT_H
            new_w = int(src_ratio * new_h)
        else:  # source too tall
            new_w = DEFAULT_W
            new_h = int(new_w / src_ratio)
        src = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - DEFAULT_W) // 2
        top = (new_h - DEFAULT_H) // 2
        src = src.crop((left, top, left + DEFAULT_W, top + DEFAULT_H))
        bg.paste(src, (0, 0))

    # Dim overlay for text
    overlay = Image.new("RGBA", (DEFAULT_W, DEFAULT_H), (0, 0, 0, 80))
    bg.paste(overlay, (0, 0), overlay)

    # Fonts (use default PIL if system fonts not present)
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
        body_font = ImageFont.truetype("DejaVuSans.ttf", 26)
        tiny_font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        tiny_font = ImageFont.load_default()

    # Text
    title = item.get("title", "Astronomy Picture of the Day")
    date_str = item.get("date", "")
    caption = (item.get("explanation") or "")[:220] + ("…" if len(item.get("explanation","")) > 220 else "")

    draw.text((36, 30), f"{title}", fill=(255, 255, 255), font=title_font)
    draw.text((36, 92), f"{date_str}", fill=(200, 210, 230), font=body_font)
    draw.text((36, 140), caption, fill=(230, 235, 245), font=body_font, spacing=4)

    # QR code
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(permalink)
    qr.make(fit=True)
    qrim = qr.make_image(fill_color="white", back_color="black").convert("RGB")
    qrim = qrim.resize((160, 160))
    bg.paste(qrim, (DEFAULT_W - 36 - 160, DEFAULT_H - 36 - 160))

    # Footer
    draw.text((36, DEFAULT_H - 48), "Made with Streamlit | APOD (NASA)", fill=(210, 220, 240), font=tiny_font)

    buf = BytesIO()
    bg.save(buf, format="PNG", compress_level=6)
    buf.seek(0)
    return buf
