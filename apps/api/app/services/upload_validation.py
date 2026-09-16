"""Shared multipart-audio-upload validation for the tracks and transitions
routes: obviously-wrong files are rejected before any decode is attempted.
"""

from pathlib import Path

from fastapi import HTTPException, UploadFile

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".wave",
    ".ogg",
    ".oga",
    ".opus",
    ".m4a",
    ".aac",
    ".flac",
    ".webm",
    ".weba",
}

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB, generous for a local track


def looks_like_audio(filename: str, content_type: str | None) -> bool:
    if content_type and content_type.startswith("audio/"):
        return True
    return Path(filename).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


async def read_validated_upload(file: UploadFile, *, label: str) -> bytes:
    """Validates `file` looks like audio and isn't empty/oversized, then
    returns its bytes. Raises HTTPException (4xx) for any violation."""
    if not file.filename:
        raise HTTPException(status_code=400, detail=f"No {label} file was provided.")

    if not looks_like_audio(file.filename, file.content_type):
        raise HTTPException(
            status_code=400,
            detail=f'"{file.filename}" is not a supported audio file.',
        )

    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail=f"{label} file is empty.")

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{label} file is too large.")

    return data
