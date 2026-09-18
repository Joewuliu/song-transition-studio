import asyncio

from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas import TrackAnalysis
from app.services.audio_analysis import AudioAnalysisError, analyze_audio
from app.services.upload_validation import read_validated_upload

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.post("/analyze", response_model=TrackAnalysis)
async def analyze_track(file: UploadFile) -> TrackAnalysis:
    data = await read_validated_upload(file, label="track")

    # analyze_audio is a plain synchronous, CPU-heavy call (librosa
    # beat/chroma/MFCC work) — running it directly here would block the
    # whole event loop for the duration, stalling every other in-flight
    # request (even /health). Offloading it to a worker thread keeps the
    # loop free; analyze_audio touches no shared mutable state, so this
    # is safe to run concurrently with other requests.
    try:
        return await asyncio.to_thread(
            analyze_audio, data, filename_hint=file.filename or ""
        )
    except AudioAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
