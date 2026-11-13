"""Shared step: generate metadata.json with the Anthropic API (transcript or script.json)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from pmfather import config
from pmfather.transcribe import Transcript, format_timestamp

MIN_CHAPTER_GAP = 10.0
MIN_CHAPTERS = 3  # YouTube only renders chapters with at least three


class Chapter(BaseModel):
    start: float = Field(ge=0)
    title: str = Field(min_length=1)
    timestamp: str = ""


class Metadata(BaseModel):
    titles: list[str] = Field(min_length=3, max_length=3)
    description: str = Field(min_length=1)
    chapters: list[Chapter] = []
    tags: list[str] = Field(min_length=1)
    thumbnail_texts: list[str] = Field(min_length=3, max_length=3)


class MetadataError(RuntimeError):
    pass


def complete(system: str, content: str | list[dict[str, Any]]) -> str:
    """Single Anthropic call. Tests replace this function; it is the only LLM network call."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.anthropic_api_key())
    message = client.messages.create(
        model=config.anthropic_model(),
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def extract_json(text: str) -> dict[str, Any]:
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the model reply")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model reply is not a JSON object")
    return data


def complete_json(system: str, content: str | list[dict[str, Any]], model_cls: type[BaseModel]):
    """Call the LLM, validate against `model_cls`; retry once on invalid output."""
    error: Exception | None = None
    for attempt in range(2):
        prompt = content
        if error is not None:
            note = (
                f"Your previous reply was invalid ({error}). "
                "Reply again with only the corrected JSON object."
            )
            prompt = (
                content + "\n\n" + note
                if isinstance(content, str)
                else [*content, {"type": "text", "text": note}]
            )
        reply = complete(system, prompt)
        try:
            return model_cls.model_validate(extract_json(reply))
        except (ValueError, ValidationError) as exc:  # JSONDecodeError is a ValueError
            error = exc
            print(f"[llm] invalid output (attempt {attempt + 1}/2): {exc}")
    raise MetadataError(f"The model returned invalid JSON twice: {error}")


def load_prompt(name: str) -> str:
    return (config.prompts_dir() / name).read_text(encoding="utf-8")


def normalize_chapters(chapters: list[Chapter], duration: float) -> list[Chapter]:
    """Sort, force the first chapter to 0:00, drop out-of-range or too-close chapters."""
    ordered = sorted(chapters, key=lambda c: c.start)
    kept: list[Chapter] = []
    for chapter in ordered:
        if duration and chapter.start >= duration:
            continue
        if kept and chapter.start - kept[-1].start < MIN_CHAPTER_GAP:
            continue
        kept.append(chapter)
    if not kept or len(kept) < MIN_CHAPTERS:
        return []
    kept[0] = kept[0].model_copy(update={"start": 0.0})
    return [c.model_copy(update={"timestamp": format_timestamp(c.start)}) for c in kept]


def format_chapters(chapters: list[Chapter]) -> str:
    return "\n".join(f"{format_timestamp(c.start)} {c.title}" for c in chapters)


def finalize(meta: Metadata, duration: float, is_short: bool) -> Metadata:
    chapters = normalize_chapters(meta.chapters, duration)
    description = meta.description.strip()
    if is_short:
        chapters = []
        if "#shorts" not in description.lower():
            description += "\n\n#Shorts"
    elif chapters:
        description += "\n\nChapters:\n" + format_chapters(chapters)
    return meta.model_copy(update={"chapters": chapters, "description": description})


def load_source(out_dir: Path) -> tuple[str, float, bool]:
    """Return (text for the LLM, duration in seconds, is_short)."""
    script_path = out_dir / "script.json"
    if script_path.exists():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        timeline_path = out_dir / "timeline.json"
        timeline = (
            json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path.exists() else []
        )
        lines = [f"Hook: {script['hook']}"]
        for i, line in enumerate(script["lines"]):
            stamp = f"[{format_timestamp(timeline[i]['start'])}] " if i < len(timeline) else ""
            lines.append(f"{stamp}Slide {i + 1}: {line}")
        duration = float(timeline[-1]["end"]) if timeline else 0.0
        text = f"Title hint: {script.get('title_hint', '')}\n" + "\n".join(lines)
        return text, duration, script.get("format") == "short"

    transcript_path = out_dir / "transcript.json"
    if not transcript_path.exists():
        raise MetadataError(
            f"No transcript.json or script.json in {out_dir}. Run a pipeline first."
        )
    transcript = Transcript.model_validate_json(transcript_path.read_text(encoding="utf-8"))
    return transcript.as_timestamped_text(), transcript.duration, False


def generate_metadata(out_dir: Path) -> Metadata:
    path = out_dir / "metadata.json"
    if path.exists():
        print(f"[metadata] skip, {path} already exists")
        return Metadata.model_validate_json(path.read_text(encoding="utf-8"))

    source, duration, is_short = load_source(out_dir)
    system = load_prompt("style_guide.md")
    task = "\n\n---\n\n".join(load_prompt(n) for n in ("title.md", "description.md", "chapters.md"))
    instructions = (
        f"{task}\n\n---\n\nReturn ONE JSON object combining the keys of all sections above "
        "(titles, thumbnail_texts, description, tags, chapters) and nothing else.\n"
    )
    if is_short:
        instructions += "This is a YouTube Short (under 60 seconds): chapters may be empty.\n"
    content = f"{instructions}\n## Video content\n\n{source}"

    meta = finalize(complete_json(system, content, Metadata), duration, is_short)
    path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta
