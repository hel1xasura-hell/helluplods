"""Thumbnail rendering with Pillow: a real screenshot (or plain background) + editable text + branding."""
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = (1280, 720)
TEMPLATES = ("bold_left", "centered", "bottom_band")
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    raise RuntimeError("No usable font found. Install fonts-dejavu-core.")


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        trial = f"{cur} {w}".strip()
        if cur and draw.textlength(trial, font=font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def render_thumbnail(text: str, template: str = "bold_left", accent: str = "#8d6bff", background: str = "#0f0e13",
                     screenshot: bytes | None = None, brand: str | None = None) -> bytes:
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template {template}")
    text = " ".join(text.split())[:80]
    if not text:
        raise ValueError("Thumbnail text is required")
    W, H = SIZE
    if screenshot:
        img = Image.open(io.BytesIO(screenshot)).convert("RGB")
        scale = max(W / img.width, H / img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        img = img.crop(((img.width - W) // 2, (img.height - H) // 2, (img.width - W) // 2 + W, (img.height - H) // 2 + H))
        img = img.filter(ImageFilter.GaussianBlur(3))
    else:
        img = Image.new("RGB", SIZE, _hex(background))
    shade = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    rgb = _hex(background)
    if template == "bold_left":
        for x in range(W):
            alpha = int(235 * max(0.0, 1 - x / (W * 0.85)))
            sd.line([(x, 0), (x, H)], fill=(*rgb, alpha))
    elif template == "centered":
        sd.rectangle([0, 0, W, H], fill=(*rgb, 170))
    else:
        sd.rectangle([0, int(H * 0.58), W, H], fill=(*rgb, 235))
    img = Image.alpha_composite(img.convert("RGBA"), shade)
    d = ImageDraw.Draw(img)

    size = 118 if len(text) <= 24 else 92 if len(text) <= 44 else 74
    font = _font(size)
    max_w = int(W * (0.56 if template == "bold_left" else 0.84))
    lines = _wrap(d, text, font, max_w)
    while len(lines) > 4 and size > 48:
        size -= 8
        font = _font(size)
        lines = _wrap(d, text, font, max_w)
    lh = int(size * 1.12)
    block_h = lh * len(lines)
    if template == "bold_left":
        x0, y0, align = 70, (H - block_h) // 2, "left"
    elif template == "centered":
        x0, y0, align = W // 2, (H - block_h) // 2, "center"
    else:
        x0, y0, align = W // 2, int(H * 0.58) + (int(H * 0.42) - block_h) // 2, "center"
    for i, line in enumerate(lines):
        w = d.textlength(line, font=font)
        x = x0 if align == "left" else x0 - w / 2
        d.text((x + 4, y0 + i * lh + 4), line, font=font, fill=(0, 0, 0, 200))
        d.text((x, y0 + i * lh), line, font=font, fill=(255, 255, 255, 255))
    d.rectangle([0, 0, 18, H], fill=(*_hex(accent), 255))
    if brand:
        bf = _font(34)
        bw = d.textlength(brand, font=bf)
        d.rounded_rectangle([W - bw - 56, 34, W - 24, 90], radius=14, fill=(*_hex(accent), 255))
        d.text((W - bw - 40, 42), brand, font=bf, fill=(255, 255, 255, 255))
    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
