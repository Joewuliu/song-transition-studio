from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas import TrackAnalysis
from app.services.audio_analysis import AudioAnalysisError, analyze_audio

router = APIRouter(prefix="/tracks", tags=["tracks"])

# Mirrors the frontend's supported-extension fallback (src/lib/audio.ts) so
# obviously wrong files (e.g. images, text) are rejected before any decode
# attempt, even if the browser sent a generic/missing content type.
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


def _looks_like_audio(filename: str, content_type: str | None) -> bool:
    if content_type and content_type.startswith("audio/"):
        return True
    return Path(filename).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


@router.post("/analyze", response_model=TrackAnalysis)
async def analyze_track(file: UploadFile) -> TrackAnalysis:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was provided.")

    if not _looks_like_audio(file.filename, file.content_type):
        raise HTTPException(
            status_code=400,
            detail=f'"{file.filename}" is not a supported audio file.',
        )

    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large.")

    try:
        return analyze_audio(data, filename_hint=file.filename)
    except AudioAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
