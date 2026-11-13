"""Pipeline B step 5: render the slideshow with ffmpeg (Ken Burns, crossfades, captions, audio)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from pmfather import config
from pmfather.edit import require_tool, run
from pmfather.transcribe import write_srt
from pmfather.voiceover import narration_texts

FPS = 30
SHORT_MAX_SECONDS = 60.0
MAX_FADE = 0.5
MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
RESOLUTIONS = {"video": (1920, 1080), "short": (1080, 1920)}


class ShortTooLongError(ValueError):
    pass


def resolution(fmt: str) -> tuple[int, int]:
    return RESOLUTIONS[fmt]


def check_short_length(total_seconds: float) -> None:
    if total_seconds > SHORT_MAX_SECONDS:
        raise ShortTooLongError(
            f"A Short must be at most {SHORT_MAX_SECONDS:.0f}s but this one would be "
            f"{total_seconds:.1f}s. Use fewer slides or shorter slide times/narration, "
            "or render with --format video."
        )


def find_music() -> Path | None:
    music_dir = config.assets_dir() / "music"
    if not music_dir.is_dir():
        return None
    tracks = sorted(p for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_EXTS)
    return tracks[0] if tracks else None


def split_caption(text: str, max_words: int = 7) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def caption_entries(texts: list[str], durations: list[float]) -> list[tuple[float, float, str]]:
    entries: list[tuple[float, float, str]] = []
    start = 0.0
    for text, duration in zip(texts, durations, strict=True):
        chunks = split_caption(text)
        total_words = sum(len(c.split()) for c in chunks) or 1
        cursor = start
        for chunk in chunks:
            length = duration * len(chunk.split()) / total_words
            entries.append((cursor, cursor + length, chunk))
            cursor += length
        start += duration
    return entries


def build_filter_graph(
    durations: list[float],
    fmt: str,
    audio_inputs: list[int],
    track: bool,
    music_input: int | None,
    fontsdir: Path | None = None,
) -> str:
    """Video: blurred background + fitted image + Ken Burns, xfade chain, burned-in captions.

    Each clip is extended by the fade length so the xfade chain keeps slide i starting at the
    sum of the previous durations, which keeps narration and visuals aligned.
    """
    w, h = resolution(fmt)
    n = len(durations)
    fade = min(MAX_FADE, 0.4 * min(durations))
    total = sum(durations)
    parts: list[str] = []

    for i, d in enumerate(durations):
        frames = math.ceil((d + (fade if i < n - 1 else 0)) * FPS)
        step = 0.12 / frames
        if i % 2 == 0:
            zoom = f"min(zoom+{step:.6f},1.12)"
        else:
            zoom = f"if(eq(on,1),1.12,max(zoom-{step:.6f},1.0))"
        parts.append(
            f"[{i}:v]split[bg{i}][fg{i}];"
            f"[bg{i}]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"boxblur=40:5[b{i}];"
            f"[fg{i}]scale={w}:{h}:force_original_aspect_ratio=decrease[f{i}];"
            f"[b{i}][f{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,scale={2 * w}:{2 * h},"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}"
            f":s={w}x{h}:fps={FPS},format=yuv420p[v{i}]"
        )

    current = "[v0]"
    start = 0.0
    for i in range(1, n):
        start += durations[i - 1]
        parts.append(
            f"{current}[v{i}]xfade=transition=fade:duration={fade:.3f}:offset={start:.3f}[x{i}]"
        )
        current = f"[x{i}]"

    style = "FontSize=16,MarginV=80" if fmt == "short" else "FontSize=14,MarginV=30"
    style += ",Alignment=2,Outline=2,Shadow=0,Bold=1"
    fonts = f":fontsdir={fontsdir}" if fontsdir else ""
    parts.append(f"{current}subtitles=captions.srt{fonts}:force_style='{style}'[vout]")

    if track:
        parts.append(
            f"[{audio_inputs[0]}:a]aresample=48000,apad=whole_dur={total:.3f},"
            f"atrim=0:{total:.3f}[narr]"
        )
    else:
        for i, (idx, d) in enumerate(zip(audio_inputs, durations, strict=True)):
            parts.append(f"[{idx}:a]aresample=48000,apad=whole_dur={d:.3f},atrim=0:{d:.3f}[a{i}]")
        joined = "".join(f"[a{i}]" for i in range(n))
        parts.append(f"{joined}concat=n={n}:v=0:a=1[narr]")
    parts.append("[narr]loudnorm=I=-16:TP=-1.5:LRA=11[nl]")

    if music_input is None:
        parts.append("[nl]anull[aout]")
    else:
        parts.append(
            f"[{music_input}:a]aresample=48000,atrim=0:{total:.3f},loudnorm=I=-22:TP=-2:LRA=11[mu]"
        )
        parts.append("[nl][mu]amix=inputs=2:duration=first:normalize=0[aout]")
    return ";".join(parts)


def render(redacted: list[Path], script: dict, voice: dict, fmt: str, out_dir: Path) -> Path:
    """Render out_dir/final.mp4 (+ captions.srt, timeline.json). Skips if final.mp4 exists."""
    final = out_dir / "final.mp4"
    if final.exists():
        print(f"[slideshow] skip, {final} already exists")
        return final

    durations: list[float] = voice["durations"]
    total = sum(durations)
    if fmt == "short":
        check_short_length(total)
    ffmpeg = require_tool("ffmpeg")

    texts = narration_texts(script)
    write_srt(caption_entries(texts, durations), out_dir / "captions.srt")
    starts = [sum(durations[:i]) for i in range(len(durations))]
    timeline = [
        {"start": s, "end": s + d, "text": t}
        for s, d, t in zip(starts, durations, texts, strict=True)
    ]
    (out_dir / "timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")

    cmd = [ffmpeg, "-y"]
    for image in redacted:
        cmd += ["-i", str(Path(image).resolve())]
    track = voice["mode"] == "track"
    audio_inputs: list[int] = []
    for path in voice["files"]:
        audio_inputs.append(len(redacted) + len(audio_inputs))
        cmd += ["-i", str(Path(path).resolve())]
    music = find_music()
    music_input = None
    if music:
        music_input = len(redacted) + len(audio_inputs)
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]

    fonts_dir = config.assets_dir() / "fonts"
    has_fonts = fonts_dir.is_dir() and any(fonts_dir.glob("*.[to]tf"))
    graph = build_filter_graph(
        durations, fmt, audio_inputs, track, music_input, fonts_dir.resolve() if has_fonts else None
    )
    cmd += [
        "-filter_complex",
        graph,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        f"{total:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(final.resolve()),
    ]
    run(cmd, cwd=out_dir)
    return final
