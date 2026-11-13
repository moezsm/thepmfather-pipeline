from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """No credentials, outputs in tmp_path, prompts from the repo."""
    for var in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "YOUTUBE_TOKEN_JSON",
        "YOUTUBE_TOKEN_FILE",
        "YOUTUBE_CLIENT_SECRET_FILE",
        "YOUTUBE_CLIENT_SECRET_JSON",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PMFATHER_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("PMFATHER_ASSETS_DIR", str(tmp_path / "no-assets"))
    return tmp_path


@pytest.fixture
def screens(tmp_path) -> Path:
    """Three tiny PNGs with a high-contrast pattern so blurring visibly changes pixels."""
    folder = tmp_path / "screens"
    folder.mkdir()
    for i in range(3):
        image = Image.new("RGB", (96, 64), "white")
        for x in range(96):
            for y in range(64):
                if (x // 3 + y // 3) % 2 == 0:
                    image.putpixel((x, y), (200 - i * 40, 20, 30 * i))
        image.save(folder / f"{i + 1:02d}.png")
    return folder


@pytest.fixture
def transcript_dir(tmp_path) -> Path:
    out = tmp_path / "output" / "demo"
    out.mkdir(parents=True)
    shutil.copy(FIXTURES / "sample_transcript.json", out / "transcript.json")
    return out


@pytest.fixture
def metadata_payload() -> dict:
    return {
        "titles": ["Plan an app with AI", "My AI backlog workflow", "Lessons from AI planning"],
        "description": "A practical look at planning an app with an AI assistant.",
        "chapters": [
            {"start": 0, "title": "Intro"},
            {"start": 40, "title": "Goals and stories"},
            {"start": 75.2, "title": "Review"},
        ],
        "tags": ["project management", "ai"],
        "thumbnail_texts": ["Plan with AI", "AI backlog", "Review it"],
    }


def dump(data) -> str:
    return json.dumps(data)
