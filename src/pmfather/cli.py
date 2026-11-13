"""pmfather command line interface."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from pmfather import config
from pmfather.config import DEFAULT_PRIVACY, Privacy

app = typer.Typer(
    help="ThePMFather video pipeline. Prepares videos; a human reviews and publishes.",
    no_args_is_help=True,
    add_completion=False,
)

DryRun = Annotated[
    bool,
    typer.Option("--dry-run", help="Do everything except the upload; print what would be sent."),
]
PrivacyOpt = Annotated[
    Privacy,
    typer.Option("--privacy", help="YouTube privacy status. 'public' only when set explicitly."),
]
VideoPath = Annotated[Path, typer.Argument(help="Path to the video file.")]


def video_name(path: Path) -> str:
    return path.name if path.is_dir() else path.stem


def final_video(path: Path, out_dir: Path) -> Path:
    produced = out_dir / "final.mp4"
    if produced.exists():
        return produced
    if path.is_file():
        return path
    raise FileNotFoundError(f"No final video in {out_dir}. Run the pipeline first.")


def guarded(func: Callable[[], None]) -> None:
    """Show known errors as clean messages instead of tracebacks."""
    try:
        func()
    except typer.Exit:
        raise
    except (
        FileNotFoundError,
        ValueError,  # includes pydantic validation errors
        RuntimeError,  # ConfigError, MetadataError, ToolMissingError
        subprocess.CalledProcessError,
    ) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc


def warn_if_public(privacy: Privacy) -> None:
    if privacy == Privacy.public:
        typer.secho("Warning: privacy is PUBLIC (explicit flag).", fg=typer.colors.YELLOW, err=True)


def metadata_and_upload(source: Path, privacy: Privacy, dry_run: bool, out_dir: Path) -> None:
    from pmfather.metadata import generate_metadata
    from pmfather.upload import upload as do_upload

    generate_metadata(out_dir)
    do_upload(final_video(source, out_dir), out_dir, privacy, dry_run)


@app.command("run")
def run_pipeline(
    video_path: VideoPath, dry_run: DryRun = False, privacy: PrivacyOpt = DEFAULT_PRIVACY
) -> None:
    """Full recording pipeline: edit -> transcribe -> metadata -> upload."""

    def work() -> None:
        from pmfather.edit import edit as do_edit
        from pmfather.transcribe import transcribe as do_transcribe

        warn_if_public(privacy)
        out_dir = config.output_dir_for(video_name(video_path))
        # Transcribe the edited video so captions and chapter times match what is uploaded.
        final = do_edit(video_path, out_dir)
        do_transcribe(final, out_dir)
        metadata_and_upload(video_path, privacy, dry_run, out_dir)

    guarded(work)


@app.command()
def transcribe(video_path: VideoPath) -> None:
    """Transcribe a video (transcript.json + captions.srt)."""

    def work() -> None:
        from pmfather.transcribe import transcribe as do_transcribe

        out_dir = config.output_dir_for(video_name(video_path))
        do_transcribe(final_video(video_path, out_dir), out_dir)

    guarded(work)


@app.command()
def edit(video_path: VideoPath) -> None:
    """Cut silences, normalise loudness, add intro/outro (writes final.mp4)."""

    def work() -> None:
        from pmfather.edit import edit as do_edit

        do_edit(video_path, config.output_dir_for(video_name(video_path)))

    guarded(work)


@app.command()
def metadata(video_path: VideoPath) -> None:
    """Generate metadata.json (needs transcript.json or script.json already in output/)."""

    def work() -> None:
        from pmfather.metadata import generate_metadata

        generate_metadata(config.output_dir_for(video_name(video_path)))

    guarded(work)


@app.command()
def thumbnail(
    video_path: VideoPath,
    text: Annotated[
        str | None, typer.Option(help="Thumbnail text (default: first idea in metadata.json).")
    ] = None,
) -> None:
    """Optional: grab a frame and overlay thumbnail text (writes thumbnail.jpg)."""

    def work() -> None:
        from pmfather.metadata import Metadata
        from pmfather.thumbnail import make_thumbnail

        out_dir = config.output_dir_for(video_name(video_path))
        chosen = text
        if not chosen:
            path = out_dir / "metadata.json"
            chosen = Metadata.model_validate_json(path.read_text("utf-8")).thumbnail_texts[0]
        make_thumbnail(final_video(video_path, out_dir), chosen, out_dir)

    guarded(work)


@app.command()
def upload(
    video_path: VideoPath, dry_run: DryRun = False, privacy: PrivacyOpt = DEFAULT_PRIVACY
) -> None:
    """Upload the final video and captions (needs metadata.json)."""

    def work() -> None:
        from pmfather.upload import upload as do_upload

        warn_if_public(privacy)
        out_dir = config.output_dir_for(video_name(video_path))
        do_upload(final_video(video_path, out_dir), out_dir, privacy, dry_run)

    guarded(work)


@app.command("from-screens")
def from_screens(
    folder: Annotated[
        Path, typer.Argument(help="Folder of screenshots (+ optional storyboard.yaml).")
    ],
    format: Annotated[
        str | None, typer.Option("--format", help="short | video (default: storyboard or video).")
    ] = None,
    voice: Annotated[
        str | None, typer.Option("--voice", help="tts | file:<path> (default: storyboard or tts).")
    ] = None,
    no_sensitive_data: Annotated[
        bool,
        typer.Option(
            "--no-sensitive-data",
            help="Confirm the screenshots hold no sensitive data; needed when slides have no blur.",
        ),
    ] = False,
    dry_run: DryRun = False,
    privacy: PrivacyOpt = DEFAULT_PRIVACY,
) -> None:
    """Full screenshots pipeline: redact, script, voiceover, render, metadata, upload."""

    def work() -> None:
        from pmfather import redact as redact_mod
        from pmfather import script_gen, slideshow, voiceover
        from pmfather.storyboard import load_storyboard

        if format not in (None, "short", "video"):
            raise ValueError("--format must be 'short' or 'video'")
        warn_if_public(privacy)

        board = load_storyboard(folder, format, voice)  # type: ignore[arg-type]
        unblurred = board.slides_without_blur()
        if unblurred and not no_sensitive_data:
            names = ", ".join(s.image for s in unblurred)
            typer.secho(
                f"Warning: no blur regions for: {names}\n"
                "Screenshots often contain API keys, emails, tokens or client names. Add `blur` "
                "regions in storyboard.yaml, or pass --no-sensitive-data to confirm there is "
                "nothing sensitive.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            raise typer.Exit(2)

        out_dir = config.output_dir_for(folder.name)
        redacted = redact_mod.redact(folder, board, out_dir)
        script = script_gen.generate_script(board, redacted, out_dir)
        voice_plan = voiceover.generate_voiceover(
            script, [s.seconds for s in board.slides], board.voice, out_dir
        )
        slideshow.render(redacted, script, voice_plan, board.format, out_dir)
        metadata_and_upload(folder, privacy, dry_run, out_dir)

    guarded(work)


if __name__ == "__main__":
    app()
