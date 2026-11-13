"""Configuration read from environment variables. Nothing is hardcoded except safe defaults."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path


class Privacy(StrEnum):
    private = "private"
    unlisted = "unlisted"
    public = "public"


DEFAULT_PRIVACY = Privacy.private


class ConfigError(RuntimeError):
    """Raised when a required setting is missing."""


def _path(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or default)


def output_root() -> Path:
    return _path("PMFATHER_OUTPUT_DIR", "output")


def assets_dir() -> Path:
    return _path("PMFATHER_ASSETS_DIR", "assets")


def prompts_dir() -> Path:
    env = os.environ.get("PMFATHER_PROMPTS_DIR")
    if env:
        return Path(env)
    # prompts/ lives at the repository root, next to src/
    return Path(__file__).resolve().parents[2] / "prompts"


def whisper_model() -> str:
    return os.environ.get("WHISPER_MODEL") or "small"


def tts_voice() -> str:
    return os.environ.get("TTS_VOICE") or "en-US-AndrewNeural"


def anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ConfigError("ANTHROPIC_API_KEY is not set.")
    return key


def anthropic_model() -> str:
    model = os.environ.get("ANTHROPIC_MODEL")
    if not model:
        raise ConfigError("ANTHROPIC_MODEL is not set (the model name is never hardcoded).")
    return model


def output_dir_for(name: str) -> Path:
    """Per-video working directory: output/<video-name>/ (created on demand)."""
    path = output_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path
