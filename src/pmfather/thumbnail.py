"""Optional: grab a frame from the final video and overlay thumbnail text."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pmfather import config
from pmfather.edit import probe_duration, require_tool, run


def find_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """First .ttf/.otf in assets/fonts, else Pillow's built-in font (assets are optional)."""
    fonts_dir = config.assets_dir() / "fonts"
    candidates = (
        sorted([*fonts_dir.glob("*.ttf"), *fonts_dir.glob("*.otf")]) if fonts_dir.is_dir() else []
    )
    if candidates:
        return ImageFont.truetype(str(candidates[0]), size)
    return ImageFont.load_default(size=size)


def overlay_text(frame: Path, text: str, out: Path) -> Path:
    image = Image.open(frame).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = find_font(max(24, image.height // 6))
    box = draw.multiline_textbbox((0, 0), text, font=font, stroke_width=6)
    x = max(20, (image.width - (box[2] - box[0])) // 2)
    y = image.height - (box[3] - box[1]) - image.height // 10
    draw.multiline_text(
        (x, y), text, font=font, fill="white", stroke_width=6, stroke_fill="black", align="center"
    )
    image.save(out, quality=92)
    return out


def make_thumbnail(video: Path, text: str, out_dir: Path) -> Path:
    out = out_dir / "thumbnail.jpg"
    if out.exists():
        print(f"[thumbnail] skip, {out} already exists")
        return out
    frame = out_dir / "thumbnail_frame.jpg"
    at = probe_duration(video) * 0.15
    run(
        [
            require_tool("ffmpeg"),
            "-y",
            "-ss",
            f"{at:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(frame),
        ]
    )
    overlay_text(frame, text, out)
    frame.unlink(missing_ok=True)
    return out
