"""Step A2: cut silences (auto-editor), normalise loudness (-16 LUFS), add intro/outro."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pmfather import config

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm"}


class ToolMissingError(RuntimeError):
    pass


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ToolMissingError(f"'{name}' was not found on PATH. See the README to install it.")
    return path


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            require_tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(out.stdout.strip())


def bumper(name: str) -> Path | None:
    """assets/intro.mp4 or assets/outro.mp4 when present (they are optional)."""
    path = config.assets_dir() / name
    return path if path.is_file() else None


def build_concat_command(clips: list[Path], out: Path) -> list[str]:
    """Re-encode every clip to 1920x1080 / 30 fps / 48 kHz stereo and concatenate them."""
    cmd = [require_tool("ffmpeg"), "-y"]
    for clip in clips:
        cmd += ["-i", str(clip)]
    parts = []
    for i in range(len(clips)):
        parts.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}];"
            f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]"
        )
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(clips)))
    graph = ";".join(parts) + f";{joined}concat=n={len(clips)}:v=1:a=1[v][a]"
    cmd += [
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        str(out),
    ]
    return cmd


def edit(video: Path, out_dir: Path) -> Path:
    """Produce out_dir/final.mp4. Skips if it already exists."""
    final = out_dir / "final.mp4"
    if final.exists():
        print(f"[edit] skip, {final} already exists")
        return final

    require_tool("ffmpeg")
    require_tool("auto-editor")
    work = out_dir / "work"
    work.mkdir(exist_ok=True)

    cut = work / "cut.mp4"
    run(["auto-editor", str(video), "--margin", "0.2sec", "--no-open", "-o", str(cut)])

    loud = work / "loudnorm.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(cut),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(loud),
        ]
    )

    clips = [p for p in (bumper("intro.mp4"), loud, bumper("outro.mp4")) if p]
    if len(clips) == 1:
        shutil.move(str(loud), final)
    else:
        run(build_concat_command(clips, final))
    shutil.rmtree(work, ignore_errors=True)
    return final
