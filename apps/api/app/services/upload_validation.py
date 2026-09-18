"""Shared multipart-audio-upload validation for the tracks and transitions
routes: obviously-wrong files are rejected before any decode is attempted.
"""

from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_max_upload_bytes

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

# Read in bounded chunks (rather than a single file.read()) so an
# oversized upload is rejected as soon as the configured limit is
# crossed, instead of after the whole body has already been buffered
# into memory — see get_max_upload_bytes() in app/config.py. /transitions/
# render accepts TWO uploads in one request, so worst-case per-request
# memory is roughly twice the per-file limit even with this bound.
_READ_CHUNK_BYTES = 1024 * 1024  # 1 MB

# Bounds the suffix used for a temp file derived from an uploaded
# filename (see safe_temp_suffix). looks_like_audio already requires
# either an audio/* content type or a short known extension, but content
# type is attacker-controlled, so this stays as cheap defense-in-depth
# against a degenerate filename producing an OS-level "name too long"
# error instead of a clean, handled response.
_MAX_TEMP_SUFFIX_LENGTH = 16


def looks_like_audio(filename: str, content_type: str | None) -> bool:
    if content_type and content_type.startswith("audio/"):
        return True
    return Path(filename).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def safe_temp_suffix(filename: str) -> str:
    """A short, filesystem-safe suffix for a temp file derived from an
    uploaded filename. `Path.suffix` already strips any directory
    component (no path-traversal risk from a hostile filename); this
    additionally length-bounds it."""
    return Path(filename).suffix[:_MAX_TEMP_SUFFIX_LENGTH]


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

    max_bytes = get_max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            limit_mb = max_bytes // (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"{label} file is too large (limit is {limit_mb} MB).",
            )
        chunks.append(chunk)

    data = b"".join(chunks)

    if not data:
        raise HTTPException(status_code=400, detail=f"{label} file is empty.")

    return data
