from pydantic import BaseModel, Field


class TrackAnalysis(BaseModel):
    duration_seconds: float = Field(..., ge=0)
    tempo_bpm: float = Field(..., ge=0)
    beat_count: int = Field(..., ge=0)
    beats: list[float]
