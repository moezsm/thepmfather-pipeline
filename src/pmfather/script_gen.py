"""Pipeline B step 3: narration script from redacted screenshots + notes (Anthropic vision)."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from pmfather import metadata
from pmfather.storyboard import Storyboard

MAX_IMAGE_BYTES = 4_500_000
MAX_SIDE = 1568


class Script(BaseModel):
    hook: str = Field(min_length=1)
    lines: list[str]


def image_block(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) > MAX_IMAGE_BYTES:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            data = buf.getvalue()
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


def build_content(board: Storyboard, redacted: list[Path]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{metadata.load_prompt('screenshot_script.md')}\n\n"
                f"Title hint: {board.title_hint or '(none)'}\n"
                f"Format: {board.format}\nNumber of slides: {len(board.slides)}\n"
            ),
        }
    ]
    for i, (slide, path) in enumerate(zip(board.slides, redacted, strict=True), start=1):
        if path.parent.name != "redacted":
            raise ValueError(f"Refusing to send a non-redacted image to the API: {path}")
        content.append({"type": "text", "text": f"Slide {i} note: {slide.note or '(no note)'}"})
        content.append(image_block(path))
    return content


def generate_script(board: Storyboard, redacted: list[Path], out_dir: Path) -> dict[str, Any]:
    path = out_dir / "script.json"
    if path.exists():
        print(f"[script] skip, {path} already exists")
        return json.loads(path.read_text(encoding="utf-8"))

    content = build_content(board, redacted)
    expected = len(board.slides)
    error: str | None = None
    script: Script | None = None
    for _ in range(2):
        prompt = content if error is None else [*content, {"type": "text", "text": error}]
        candidate = metadata.complete_json(metadata.load_prompt("style_guide.md"), prompt, Script)
        if len(candidate.lines) == expected:
            script = candidate
            break
        error = (
            f"Your previous reply had {len(candidate.lines)} lines but there are {expected} "
            "slides. Return exactly one line per slide."
        )
    if script is None:
        raise metadata.MetadataError(error or "invalid script")

    data = {"title_hint": board.title_hint, "format": board.format, **script.model_dump()}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
