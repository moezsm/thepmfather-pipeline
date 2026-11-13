"""Pipeline B step 4: voiceover providers and slide timing."""

from __future__ import annotations

import asyncio
import json
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from pmfather import config
from pmfather.edit import probe_duration


class VoiceProvider(ABC):
    @abstractmethod
    def synthesize(self, texts: list[str], out_dir: Path) -> list[Path]:
        """Return audio paths. One per text for per-slide voices; a single path for a full track."""


class EdgeTTSProvider(VoiceProvider):
    def __init__(self, voice: str | None = None):
        self.voice = voice or config.tts_voice()

    def synthesize(self, texts: list[str], out_dir: Path) -> list[Path]:
        import edge_tts

        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, text in enumerate(texts, start=1):
            path = out_dir / f"slide_{i:02d}.mp3"
            if not path.exists():
                asyncio.run(edge_tts.Communicate(text, self.voice).save(str(path)))
            paths.append(path)
        return paths


class FileProvider(VoiceProvider):
    """Use an existing audio file as the whole voiceover track."""

    def __init__(self, path: Path):
        if not path.is_file():
            raise FileNotFoundError(f"Voiceover file not found: {path}")
        self.path = path

    def synthesize(self, texts: list[str], out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"track{self.path.suffix}"
        shutil.copyfile(self.path, dest)
        return [dest]


def get_provider(voice: str) -> VoiceProvider:
    if voice == "tts":
        return EdgeTTSProvider()
    if voice.startswith("file:"):
        return FileProvider(Path(voice[5:]))
    raise ValueError(f"Unknown voice '{voice}'. Use 'tts' or 'file:<path>'.")


def narration_texts(script: dict) -> list[str]:
    """The hook is spoken at the start of the first slide."""
    lines = list(script["lines"])
    lines[0] = f"{script['hook'].strip()} {lines[0].strip()}"
    return lines


def plan_durations(
    seconds: list[float], audio_lengths: list[float], track: bool = False
) -> list[float]:
    """Per-slide voice: max(storyboard seconds, narration length).

    Single full track: stretch all slides proportionally if the track is longer than the plan.
    """
    if not track:
        return [max(s, a) for s, a in zip(seconds, audio_lengths, strict=True)]
    total = sum(seconds)
    factor = max(1.0, audio_lengths[0] / total)
    return [s * factor for s in seconds]


def generate_voiceover(script: dict, seconds: list[float], voice: str, out_dir: Path) -> dict:
    """Write voiceover.json {mode, files, durations}. Skips if already present."""
    manifest = out_dir / "voiceover.json"
    if manifest.exists():
        print(f"[voiceover] skip, {manifest} already exists")
        return json.loads(manifest.read_text(encoding="utf-8"))

    files = get_provider(voice).synthesize(narration_texts(script), out_dir / "voiceover")
    lengths = [probe_duration(f) for f in files]
    track = voice.startswith("file:")
    data = {
        "mode": "track" if track else "per_slide",
        "files": [str(f) for f in files],
        "durations": plan_durations(seconds, lengths, track),
    }
    manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
