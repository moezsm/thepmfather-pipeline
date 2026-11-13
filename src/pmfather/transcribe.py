"""Step A1: faster-whisper transcription -> transcript.json + captions.srt."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from pmfather import config


class Segment(BaseModel):
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: str = "en"
    duration: float = 0.0
    segments: list[Segment]

    def as_timestamped_text(self) -> str:
        return "\n".join(f"[{format_timestamp(s.start)}] {s.text.strip()}" for s in self.segments)


def format_timestamp(seconds: float) -> str:
    """YouTube chapter style: M:SS, or H:MM:SS from one hour."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_srt_time(seconds: float) -> str:
    millis = round(max(0.0, seconds) * 1000)
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def write_srt(entries: list[tuple[float, float, str]], path: Path) -> None:
    blocks = [
        f"{i}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text.strip()}\n"
        for i, (start, end, text) in enumerate(entries, start=1)
    ]
    path.write_text("\n".join(blocks), encoding="utf-8")


def transcribe(video: Path, out_dir: Path) -> Transcript:
    """Transcribe `video` into out_dir. Skips work if transcript.json and captions.srt exist."""
    json_path = out_dir / "transcript.json"
    srt_path = out_dir / "captions.srt"
    if json_path.exists() and srt_path.exists():
        print(f"[transcribe] skip, already present in {out_dir}")
        return Transcript.model_validate_json(json_path.read_text(encoding="utf-8"))

    from faster_whisper import WhisperModel  # heavy import, only when needed

    model = WhisperModel(config.whisper_model(), compute_type="int8")
    raw_segments, info = model.transcribe(str(video))
    segments = [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in raw_segments]
    transcript = Transcript(
        language=info.language, duration=float(info.duration), segments=segments
    )
    json_path.write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
    write_srt([(s.start, s.end, s.text) for s in segments], srt_path)
    return transcript
