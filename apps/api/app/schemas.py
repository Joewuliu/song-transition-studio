import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TransitionCandidate(BaseModel):
    """A beat that scored well as a potential transition entry/exit point —
    not a downbeat, bar, or phrase boundary; just a beat near a locally
    meaningful energy/onset change. `time_seconds` matches the track's
    `beats` array exactly (never a derived/rounded approximation)."""

    beat_index: int = Field(..., ge=0)
    time_seconds: float = Field(..., ge=0)
    score: float
    boundary_strength: float = Field(..., ge=0)
    energy_before: float = Field(..., ge=0)
    energy_after: float = Field(..., ge=0)


class TrackAnalysis(BaseModel):
    duration_seconds: float = Field(..., ge=0)
    tempo_bpm: float = Field(..., ge=0)
    beat_count: int = Field(..., ge=0)
    beats: list[float]
    # Small, ranked shortlists (not full frame-level feature data) — see
    # services/audio_analysis.py for how these are derived. Both roles are
    # computed for every track since a track's Song A/B role isn't known
    # at analysis time.
    entry_candidates: list[TransitionCandidate] = Field(default_factory=list)
    exit_candidates: list[TransitionCandidate] = Field(default_factory=list)


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
    transition_beats: Literal[8, 16, 32] = 16
    song_a_gain_db: float = Field(default=0.0, ge=-12.0, le=6.0)
    song_b_gain_db: float = Field(default=0.0, ge=-12.0, le=6.0)
    crossfade_bias: float = Field(default=0.0, ge=-1.0, le=1.0)
    # Applied to song_b_bpm before computing the stretch rate, so a tempo
    # tracker reporting the same pulse at half/double speed doesn't force
    # an unnecessary 2x stretch. See services/transition_planner.py.
    song_b_tempo_multiplier: Literal[0.5, 1.0, 2.0] = 1.0

    @field_validator("song_a_bpm", "song_b_bpm")
    @classmethod
    def _finite_positive_bpm(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("bpm must be a finite, positive number")
        return value


class SuggestedAnchor(BaseModel):
    beat_index: int = Field(..., ge=0)
    time_seconds: float = Field(..., ge=0)


class TransitionSuggestion(BaseModel):
    """Shaped to drop directly into the frontend's TransitionPlan — the
    manual editor and the suggestion flow share one plan representation."""

    song_a_anchor: SuggestedAnchor
    song_b_anchor: SuggestedAnchor
    transition_beats: Literal[8, 16, 32]
    song_a_gain_db: float
    song_b_gain_db: float
    crossfade_bias: float
    song_b_tempo_multiplier: Literal[0.5, 1.0, 2.0]


class TransitionSuggestRequest(BaseModel):
    """Takes the two already-computed analyses directly — suggesting a
    plan needs no raw audio, so this never re-uploads either file."""

    song_a_analysis: TrackAnalysis
    song_b_analysis: TrackAnalysis


class TransitionSuggestResponse(BaseModel):
    plan: TransitionSuggestion
    effective_song_b_bpm: float = Field(..., gt=0)
    tempo_compatibility: Literal["compatible", "moderate", "significant", "extreme"]
    used_tempo_normalization: bool
    song_a_anchor_source: Literal["candidate", "fallback"]
    song_b_anchor_source: Literal["candidate", "fallback"]
