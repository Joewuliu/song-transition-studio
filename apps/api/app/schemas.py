import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TrackAnalysis(BaseModel):
    duration_seconds: float = Field(..., ge=0)
    tempo_bpm: float = Field(..., ge=0)
    beat_count: int = Field(..., ge=0)
    beats: list[float]


class BeatAnchorIn(BaseModel):
    """A previously-selected beat anchor, as established in M3. `time_seconds`
    is trusted as-is from the client's own analysis result — rendering does
    not re-run beat detection, so the full `beats` array never needs to be
    resent here."""

    beat_index: int = Field(..., ge=0)
    time_seconds: float

    @field_validator("time_seconds")
    @classmethod
    def _finite_non_negative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("time_seconds must be a finite, non-negative number")
        return value


class TransitionRenderRequest(BaseModel):
    song_a_anchor: BeatAnchorIn
    song_b_anchor: BeatAnchorIn
    song_a_bpm: float
    song_b_bpm: float
    transition_beats: Literal[16] = 16

    @field_validator("song_a_bpm", "song_b_bpm")
    @classmethod
    def _finite_positive_bpm(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("bpm must be a finite, positive number")
        return value
