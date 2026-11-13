# Copilot instructions for thepmfather-pipeline

`pmfather` is a Python 3.11+ CLI that prepares videos for the "ThePMFather" YouTube channel
(project management with AI). A human always reviews and publishes in YouTube Studio.

## Pipelines
- A) Recording: raw video -> transcribe -> edit -> metadata -> upload
- B) Screenshots: folder -> storyboard -> redact -> script -> voiceover -> render (video|short)
  -> metadata -> upload
- Steps are idempotent: skip work already present in `output/<video-name>/`.

## Structure
`src/pmfather/` (cli, config, transcribe, edit, metadata, thumbnail, upload, storyboard, redact,
script_gen, voiceover, slideshow), `prompts/` (templates), `assets/` (optional intro/outro/music/
fonts; code must work when missing), `tests/` (+ `tests/fixtures/`), `input/` and `output/` (gitignored).

## Safety rules (strict)
- Never commit secrets. Configuration comes only from environment variables
  (ANTHROPIC_API_KEY, ANTHROPIC_MODEL, WHISPER_MODEL, YouTube OAuth paths). `.env.example` has names only.
- Never hardcode the model name.
- Default privacy is `private` everywhere. `public` only via explicit `--privacy public`.
  Never add features that publish publicly on their own.
- Screenshots may contain secrets. Only redacted copies (`output/<name>/redacted/`) may be sent to
  any API. `from-screens` warns on slides without blur and requires `--no-sensitive-data` to proceed.
- No telemetry; no network calls other than the Anthropic and YouTube APIs (edge-tts is the default
  voiceover and is the one documented exception for TTS).
- `.gitignore` must cover input/, output/, .env, token files, client_secret*.json.

## Code style
- Type hints, pydantic for validation, typer for CLI, small functions, comments only when needed.
- Lint/format with ruff (line length 100).

## Tests
Tests must run offline without credentials; mock Anthropic, TTS and YouTube.

```
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
```
