from fastapi import APIRouter, HTTPException, UploadFile

from app.schemas import TrackAnalysis
from app.services.audio_analysis import AudioAnalysisError, analyze_audio
from app.services.upload_validation import read_validated_upload

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.post("/analyze", response_model=TrackAnalysis)
async def analyze_track(file: UploadFile) -> TrackAnalysis:
    data = await read_validated_upload(file, label="track")

    try:
        return analyze_audio(data, filename_hint=file.filename or "")
    except AudioAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
