"""Pipeline B step 2: blur sensitive regions. Only redacted copies are used afterwards."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageFilter

from pmfather.storyboard import Storyboard

PIXEL_BLOCK = 12


class RedactionError(ValueError):
    pass


def apply_blur(image: Image.Image, regions: list[list[int]]) -> Image.Image:
    """Pixelate then blur each [x, y, w, h] region (clamped to the image bounds)."""
    out = image.convert("RGB")
    for x, y, w, h in regions:
        left, top = min(x, out.width), min(y, out.height)
        right, bottom = min(x + w, out.width), min(y + h, out.height)
        if right <= left or bottom <= top:
            raise RedactionError(f"Blur region {[x, y, w, h]} is outside the {out.size} image")
        crop = out.crop((left, top, right, bottom))
        small = crop.resize(
            (max(1, crop.width // PIXEL_BLOCK), max(1, crop.height // PIXEL_BLOCK)),
            Image.BILINEAR,
        )
        crop = small.resize(crop.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(8))
        out.paste(crop, (left, top))
    return out


def redacted_dir(out_dir: Path) -> Path:
    return out_dir / "redacted"


def redact(folder: Path, board: Storyboard, out_dir: Path) -> list[Path]:
    """Write redacted PNG copies to out_dir/redacted/ and return their paths, in slide order."""
    target = redacted_dir(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    paths: list[Path] = []
    for i, slide in enumerate(board.slides, start=1):
        source = folder / slide.image
        dest = target / f"{i:02d}_{source.stem}.png"
        stat = source.stat()
        signature = [stat.st_size, stat.st_mtime_ns, slide.blur]
        if dest.exists() and manifest.get(dest.name) == signature:
            paths.append(dest)
            continue
        with Image.open(source) as image:
            # Re-saving drops EXIF and other metadata from the original.
            apply_blur(image, slide.blur).save(dest, format="PNG")
        manifest[dest.name] = signature
        paths.append(dest)

    manifest_path.write_text(json.dumps(manifest, indent=2))
    return paths
