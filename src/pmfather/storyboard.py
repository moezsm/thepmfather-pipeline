"""Pipeline B step 1: read or build the storyboard for a screenshots folder."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_SECONDS = 4.0

VideoFormat = Literal["short", "video"]


class Slide(BaseModel):
    image: str
    note: str = ""
    seconds: float = Field(default=DEFAULT_SECONDS, gt=0)
    blur: list[list[int]] = []  # [x, y, width, height]

    @field_validator("blur")
    @classmethod
    def _check_regions(cls, regions: list[list[int]]) -> list[list[int]]:
        for region in regions:
            if len(region) != 4:
                raise ValueError(f"blur region must be [x, y, width, height], got {region}")
            x, y, w, h = region
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                raise ValueError(f"invalid blur region {region}")
        return regions


class Storyboard(BaseModel):
    title_hint: str = ""
    format: VideoFormat = "video"
    voice: str = "tts"
    slides: list[Slide] = Field(min_length=1)

    @field_validator("voice")
    @classmethod
    def _check_voice(cls, voice: str) -> str:
        if voice != "tts" and not (voice.startswith("file:") and len(voice) > 5):
            raise ValueError("voice must be 'tts' or 'file:<path>'")
        return voice

    def slides_without_blur(self) -> list[Slide]:
        return [s for s in self.slides if not s.blur]


def list_images(folder: Path) -> list[Path]:
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS),
        key=lambda p: p.name,
    )


def load_storyboard(
    folder: Path, fmt: VideoFormat | None = None, voice: str | None = None
) -> Storyboard:
    """storyboard.yaml if present, else one slide per image sorted by filename.

    `fmt` and `voice` (from the CLI) override the file values when given.
    """
    if not folder.is_dir():
        raise FileNotFoundError(f"Screenshots folder not found: {folder}")
    path = folder / "storyboard.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        board = Storyboard.model_validate(data)
    else:
        images = list_images(folder)
        if not images:
            raise FileNotFoundError(f"No images (png/jpg/webp) in {folder}")
        board = Storyboard(slides=[Slide(image=p.name) for p in images])

    updates = {k: v for k, v in (("format", fmt), ("voice", voice)) if v}
    if updates:
        board = Storyboard.model_validate({**board.model_dump(), **updates})
    for slide in board.slides:
        if not (folder / slide.image).is_file():
            raise FileNotFoundError(f"Slide image not found: {folder / slide.image}")
    return board
