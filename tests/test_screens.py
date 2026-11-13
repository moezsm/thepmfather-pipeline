from __future__ import annotations

import base64
import json

import pytest
from PIL import Image, ImageChops
from typer.testing import CliRunner

from pmfather import metadata, redact, script_gen, slideshow
from pmfather.cli import app
from pmfather.storyboard import load_storyboard


def test_storyboard_default_from_sorted_images(screens):
    board = load_storyboard(screens)
    assert [s.image for s in board.slides] == ["01.png", "02.png", "03.png"]
    assert board.format == "video" and board.voice == "tts"
    assert all(s.seconds == 4.0 and s.blur == [] for s in board.slides)


def test_storyboard_yaml_and_cli_override(screens):
    (screens / "storyboard.yaml").write_text(
        "title_hint: Demo\nformat: video\nvoice: tts\nslides:\n"
        "  - {image: 02.png, note: second, seconds: 5, blur: [[0, 0, 10, 10]]}\n"
        "  - {image: 01.png}\n"
    )
    board = load_storyboard(screens, fmt="short", voice="file:a.mp3")
    assert board.title_hint == "Demo"
    assert board.format == "short" and board.voice == "file:a.mp3"
    assert board.slides[0].blur == [[0, 0, 10, 10]]
    assert board.slides_without_blur()[0].image == "01.png"


def test_storyboard_rejects_bad_blur(screens):
    (screens / "storyboard.yaml").write_text("slides:\n  - {image: 01.png, blur: [[0, 0, 10]]}\n")
    with pytest.raises(ValueError):
        load_storyboard(screens)


def test_redaction_changes_only_blurred_pixels(screens, tmp_path):
    (screens / "storyboard.yaml").write_text(
        "slides:\n  - {image: 01.png, blur: [[0, 0, 48, 32]]}\n"
    )
    board = load_storyboard(screens)
    [path] = redact.redact(screens, board, tmp_path / "out")
    original = Image.open(screens / "01.png").convert("RGB")
    redacted = Image.open(path)

    assert path.parent.name == "redacted"
    assert ImageChops.difference(
        original.crop((0, 0, 48, 32)), redacted.crop((0, 0, 48, 32))
    ).getbbox()
    outside = (48, 0, 96, 64)
    assert not ImageChops.difference(original.crop(outside), redacted.crop(outside)).getbbox()


def test_only_redacted_copies_reach_the_api(screens, tmp_path, monkeypatch):
    (screens / "storyboard.yaml").write_text(
        "slides:\n  - {image: 01.png, note: a, blur: [[0, 0, 48, 32]]}\n"
    )
    board = load_storyboard(screens)
    out = tmp_path / "out"
    out.mkdir()
    redacted = redact.redact(screens, board, out)
    sent = []

    def fake(system, content):
        sent.append(content)
        return json.dumps({"hook": "Look at this", "lines": ["one"]})

    monkeypatch.setattr(metadata, "complete", fake)
    script_gen.generate_script(board, redacted, out)

    images = [b for b in sent[0] if b["type"] == "image"]
    assert len(images) == 1
    payload = base64.b64decode(images[0]["source"]["data"])
    assert payload == redacted[0].read_bytes()
    assert payload != (screens / "01.png").read_bytes()

    with pytest.raises(ValueError):
        script_gen.build_content(board, [screens / "01.png"])


def test_short_resolution_and_limit():
    assert slideshow.resolution("short") == (1080, 1920)
    assert slideshow.resolution("video") == (1920, 1080)
    slideshow.check_short_length(60.0)
    with pytest.raises(slideshow.ShortTooLongError, match="fewer slides"):
        slideshow.check_short_length(60.1)


def test_short_filter_graph_uses_vertical_canvas_with_blurred_background():
    graph = slideshow.build_filter_graph([4, 4], "short", [2, 3], False, None)
    assert "scale=1080:1920" in graph and "boxblur" in graph
    assert "xfade" in graph and "subtitles=captions.srt" in graph


def test_from_screens_requires_flag_without_blur(screens):
    result = CliRunner().invoke(app, ["from-screens", str(screens), "--format", "short"])
    assert result.exit_code == 2
    assert "--no-sensitive-data" in result.output
    assert not (screens.parent / "output" / "screens" / "redacted").exists()
