"""Shared step: upload the final video and captions to YouTube (Data API v3, OAuth)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pmfather.config import DEFAULT_PRIVACY, ConfigError, Privacy
from pmfather.metadata import Metadata

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CATEGORY_ID = "28"  # Science & Technology


def build_request_body(meta: Metadata, privacy: Privacy = DEFAULT_PRIVACY) -> dict[str, Any]:
    """Body for videos.insert. Uses the first title option and the generated description."""
    return {
        "snippet": {
            "title": meta.titles[0][:100],
            "description": meta.description,
            "tags": meta.tags,
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": Privacy(privacy).value,
            "selfDeclaredMadeForKids": False,
        },
    }


def load_credentials():
    """OAuth credentials from env: token (JSON content or file) and client secret (JSON or file)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_file = Path(os.environ.get("YOUTUBE_TOKEN_FILE") or "token.json")
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    creds = None
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if not token_json:
            token_file.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if token_json:
        raise ConfigError("YOUTUBE_TOKEN_JSON is invalid or has no refresh token.")
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret_json = os.environ.get("YOUTUBE_CLIENT_SECRET_JSON")
    secret_file = os.environ.get("YOUTUBE_CLIENT_SECRET_FILE")
    if secret_json:
        flow = InstalledAppFlow.from_client_config(json.loads(secret_json), SCOPES)
    elif secret_file:
        flow = InstalledAppFlow.from_client_secrets_file(secret_file, SCOPES)
    else:
        raise ConfigError(
            "Set YOUTUBE_CLIENT_SECRET_FILE (or YOUTUBE_CLIENT_SECRET_JSON) to authorize YouTube."
        )
    creds = flow.run_local_server(port=0)
    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_service():
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=load_credentials())


def resumable_upload(request) -> dict[str, Any]:
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"[upload] {int(status.progress() * 100)}%")
    return response


def upload(
    video: Path,
    out_dir: Path,
    privacy: Privacy = DEFAULT_PRIVACY,
    dry_run: bool = False,
    service: Any = None,
) -> str | None:
    """Upload video + captions. Returns the video id, or None for a dry run."""
    meta = Metadata.model_validate_json((out_dir / "metadata.json").read_text(encoding="utf-8"))
    body = build_request_body(meta, privacy)
    captions = out_dir / "captions.srt"

    if dry_run:
        print("[dry-run] Nothing is uploaded. Would send:")
        print(f"  video:    {video}")
        print(f"  captions: {captions if captions.exists() else '(none)'}")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return None

    marker = out_dir / "upload.json"
    if marker.exists():
        video_id = json.loads(marker.read_text(encoding="utf-8"))["video_id"]
        print(f"[upload] skip, already uploaded as {video_id}")
        return video_id

    from googleapiclient.http import MediaFileUpload

    service = service or build_service()
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True),
    )
    video_id = resumable_upload(request)["id"]
    marker.write_text(
        json.dumps({"video_id": video_id, "privacy": body["status"]["privacyStatus"]}),
        encoding="utf-8",
    )

    if captions.exists():
        service.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "language": "en", "name": "English"}},
            media_body=MediaFileUpload(str(captions), mimetype="application/octet-stream"),
        ).execute()

    thumb = out_dir / "thumbnail.jpg"
    if thumb.exists():
        try:
            service.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(str(thumb))
            ).execute()
        except Exception as exc:  # custom thumbnails need a verified channel
            print(f"[upload] thumbnail not set: {exc}")

    print(f"[upload] done: https://studio.youtube.com/video/{video_id}/edit (review and publish)")
    return video_id
