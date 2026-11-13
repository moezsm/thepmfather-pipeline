from __future__ import annotations

import json
from pathlib import Path

import pytest

from pmfather import metadata
from pmfather.config import DEFAULT_PRIVACY, Privacy
from pmfather.transcribe import format_timestamp

from .conftest import dump


def test_chapter_timestamp_formatting():
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(75.9) == "1:15"
    assert format_timestamp(3600) == "1:00:00"
    assert format_timestamp(3725) == "1:02:05"


def test_metadata_written_with_chapters(monkeypatch, transcript_dir, metadata_payload):
    monkeypatch.setattr(metadata, "complete", lambda system, content: dump(metadata_payload))
    meta = metadata.generate_metadata(transcript_dir)

    assert (transcript_dir / "metadata.json").exists()
    assert "Chapters:\n0:00 Intro\n0:40 Goals and stories\n1:15 Review" in meta.description
    assert [c.timestamp for c in meta.chapters] == ["0:00", "0:40", "1:15"]
    assert len(meta.titles) == 3 and len(meta.thumbnail_texts) == 3


def test_metadata_retries_once_on_invalid_output(monkeypatch, transcript_dir, metadata_payload):
    replies = iter(["not json at all", "```json\n" + dump(metadata_payload) + "\n```"])
    calls = []

    def fake(system, content):
        calls.append(content)
        return next(replies)

    monkeypatch.setattr(metadata, "complete", fake)
    meta = metadata.generate_metadata(transcript_dir)
    assert len(calls) == 2
    assert meta.titles[0] == "Plan an app with AI"


def test_metadata_fails_after_second_invalid_reply(monkeypatch, transcript_dir, metadata_payload):
    bad = {**metadata_payload, "titles": ["only one"]}
    calls = []
    monkeypatch.setattr(metadata, "complete", lambda s, c: calls.append(1) or dump(bad))
    with pytest.raises(metadata.MetadataError):
        metadata.generate_metadata(transcript_dir)
    assert len(calls) == 2


def test_short_gets_shorts_hashtag(monkeypatch, tmp_path, metadata_payload):
    out = tmp_path / "output" / "s"
    out.mkdir(parents=True)
    (out / "script.json").write_text(
        json.dumps({"title_hint": "x", "format": "short", "hook": "h", "lines": ["a"]})
    )
    monkeypatch.setattr(metadata, "complete", lambda s, c: dump(metadata_payload))
    meta = metadata.generate_metadata(out)
    assert meta.description.endswith("#Shorts")
    assert meta.chapters == []


def test_privacy_default_is_private():
    assert DEFAULT_PRIVACY == Privacy.private
    from pmfather.upload import build_request_body

    meta = metadata.Metadata(
        titles=["a", "b", "c"],
        description="d",
        tags=["t"],
        thumbnail_texts=["x", "y", "z"],
    )
    assert build_request_body(meta)["status"]["privacyStatus"] == "private"
    assert build_request_body(meta)["snippet"]["title"] == "a"


def test_dry_run_does_not_upload(monkeypatch, transcript_dir, metadata_payload, capsys):
    from pmfather import upload as upload_mod

    meta = metadata.finalize(metadata.Metadata.model_validate(metadata_payload), 130.0, False)
    (transcript_dir / "metadata.json").write_text(meta.model_dump_json())

    def boom(*args, **kwargs):
        raise AssertionError("upload must not be called in dry-run")

    monkeypatch.setattr(upload_mod, "build_service", boom)
    monkeypatch.setattr(upload_mod, "load_credentials", boom)

    result = upload_mod.upload(Path("video.mp4"), transcript_dir, Privacy.private, dry_run=True)
    assert result is None
    assert '"privacyStatus": "private"' in capsys.readouterr().out
    assert not (transcript_dir / "upload.json").exists()


def test_cli_dry_run_runs_without_upload(monkeypatch, tmp_path, transcript_dir, metadata_payload):
    from typer.testing import CliRunner

    from pmfather import upload as upload_mod
    from pmfather.cli import app

    video = tmp_path / "demo.mp4"
    video.write_bytes(b"x")
    (transcript_dir / "final.mp4").write_bytes(b"x")  # edit step is skipped (idempotent)
    (transcript_dir / "captions.srt").write_text("")  # so is transcription
    monkeypatch.setattr(metadata, "complete", lambda s, c: dump(metadata_payload))
    monkeypatch.setattr(upload_mod, "build_service", lambda: pytest.fail("uploaded"))

    result = CliRunner().invoke(app, ["run", str(video), "--dry-run"])
    # transcript.json is already present so transcription is skipped too
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
