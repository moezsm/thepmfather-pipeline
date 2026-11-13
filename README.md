# ThePMFather pipeline

project management with AI: how I use AI tools to create, develop and manage apps.

`pmfather` prepares videos for the channel. **A human always reviews and publishes manually in
YouTube Studio.** Uploads are `private` by default; `public` only happens with an explicit
`--privacy public`.

Two pipelines share the same metadata and upload steps:

- **A) Recording**: raw screen recording -> edit -> transcribe -> metadata -> upload
- **B) Screenshots**: folder of screenshots -> redact -> script -> voiceover -> render (video or
  Short) -> metadata -> upload

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # then fill in values; .env is gitignored
```

The CLI reads environment variables only (it does not load `.env` itself), so export them:
`set -a; . ./.env; set +a`.

### Install ffmpeg
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- Windows: `winget install Gyan.FFmpeg`

`auto-editor` is installed by pip. Check with `ffmpeg -version`.

### Anthropic API key
Create a key in the [Anthropic Console](https://console.anthropic.com/) and set
`ANTHROPIC_API_KEY`. Set `ANTHROPIC_MODEL` to the model name you want to use (it is never
hardcoded). Optional: `WHISPER_MODEL` (default `small`), `TTS_VOICE` (edge-tts voice name).

### YouTube OAuth credentials
1. In [Google Cloud Console](https://console.cloud.google.com/) create a project and enable
   **YouTube Data API v3**.
2. Configure the OAuth consent screen and add yourself as a test user.
3. Create credentials -> **OAuth client ID** -> application type **Desktop app**; download the JSON.
4. Point `YOUTUBE_CLIENT_SECRET_FILE` at it (keep it outside git; `client_secret*.json` is ignored).
5. The first upload opens a browser for consent and saves a token to `YOUTUBE_TOKEN_FILE`
   (default `token.json`, gitignored).

> **Unverified API projects:** YouTube restricts videos uploaded through API projects that have not
> passed the API compliance audit to **private** only. Until your project is verified, uploads stay
> private and you publish from YouTube Studio. That matches this tool's default.

### GitHub secrets (for `publish.yml`)
`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `WHISPER_MODEL` (may be empty string), 
`YOUTUBE_CLIENT_SECRET_JSON` (contents of the client secret file) and `YOUTUBE_TOKEN_JSON`
(contents of the `token.json` created by a local first run; CI cannot open a browser).
The workflow is `workflow_dispatch` only and always uploads as private.

## Usage

Global flags (accepted by `run`, `upload` and `from-screens`): `--dry-run` (everything except the
upload, prints what would be sent) and `--privacy private|unlisted|public` (default `private`).
Every step skips work already present in `output/<video-name>/`; delete a file there to redo it.

```bash
# A) Recording
pmfather run input/demo.mp4 --dry-run
pmfather edit input/demo.mp4
pmfather transcribe input/demo.mp4
pmfather metadata input/demo.mp4
pmfather thumbnail input/demo.mp4          # optional
pmfather upload input/demo.mp4 --privacy private

# B) Screenshots
pmfather from-screens input/my-demo --format short
pmfather from-screens input/my-demo --format video --voice file:input/voice.mp3
pmfather from-screens input/my-demo --format video --no-sensitive-data
```

Outputs per video are in `output/<video-name>/`: `final.mp4`, `transcript.json`, `captions.srt`,
`metadata.json` (3 titles, description with chapters, tags, 3 thumbnail texts), and for pipeline B
also `redacted/`, `script.json`, `voiceover.json`, `timeline.json`.

### Sample `storyboard.yaml`
```yaml
title_hint: Planning an app backlog with an AI assistant
format: short          # short | video (overridden by --format)
voice: tts             # tts | file:<path> (overridden by --voice)
slides:
  - image: 01-board.png
    note: The empty backlog board before I start.
    seconds: 4
    blur: [[40, 20, 300, 60]]        # [x, y, width, height]
  - image: 02-prompt.png
    note: The prompt I give the assistant.
    seconds: 5
    blur: [[0, 700, 1920, 40], [900, 100, 400, 50]]
```
Without a `storyboard.yaml`, one slide per image (sorted by filename, 4 s each) is used.

### Safety with screenshots
Screenshots often contain secrets (API keys, emails, tokens, client names). `from-screens` blurs the
`blur` regions into `output/<name>/redacted/` and **only the redacted copies** are sent to the API
or rendered. If any slide has no blur region the command warns and stops; pass
`--no-sensitive-data` to confirm there is nothing sensitive.

### Optional assets
`assets/intro.mp4`, `assets/outro.mp4` (need an audio track), `assets/music/` (first track is used at
about -22 LUFS) and `assets/fonts/` (`.ttf`/`.otf`). Everything works when they are missing.

## Development
```bash
ruff check . && ruff format --check .
pytest -q          # offline; Anthropic, TTS and YouTube are mocked
```

## Network use
Only the Anthropic and YouTube APIs are called by the pipeline, plus two unavoidable
dependencies: edge-tts (the default voiceover) contacts Microsoft's speech service, and
faster-whisper downloads the model on first use (set `WHISPER_MODEL` to a local path to avoid it).
Use `--voice file:<path>` to avoid TTS network use. No telemetry.

