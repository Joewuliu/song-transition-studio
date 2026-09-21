import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.transition_renderer import _valid_bass_swap_range

PitchClass = Literal["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
Mode = Literal["major", "minor"]
TransitionStyle = Literal["smooth", "bass_swap"]
BassSwapWidthBeats = Literal[2, 4, 8]


class TransitionCandidate(BaseModel):
    """A beat that scored well as a potential transition entry/exit point —
    not a downbeat, bar, or phrase boundary; just a beat near a locally
    meaningful energy/onset/structural change. `time_seconds` matches the
    track's `beats` array exactly (never a derived/rounded approximation).

    `local_key`/`local_mode`/`local_key_confidence` describe an estimated
    key/mode of a small window around this specific beat, not the whole
    track — see GLOBAL vs LOCAL key estimation in audio_analysis.py. Either
    can be null when the local signal is too weak/ambiguous to trust."""

    beat_index: int = Field(..., ge=0)
    time_seconds: float = Field(..., ge=0)
    score: float
    boundary_strength: float = Field(..., ge=0)
    energy_before: float = Field(..., ge=0)
    energy_after: float = Field(..., ge=0)
    structure_strength: float = Field(default=0.0, ge=0, le=1)
    local_key: PitchClass | None = None
    local_mode: Mode | None = None
    local_key_confidence: float = Field(default=0.0, ge=0, le=1)
    # A compact local MFCC summary (mean of 13 coefficients) around this
    # beat — see services/audio_analysis._local_timbre_at. Used by M12's
    # pairwise planner for cross-track timbral/spectral compatibility; null
    # whenever chroma/MFCC extraction itself failed (see TrackAnalysis).
    local_timbre: list[float] | None = None


class TrackAnalysis(BaseModel):
    duration_seconds: float = Field(..., ge=0)
    tempo_bpm: float = Field(..., ge=0)
    beat_count: int = Field(..., ge=0)
    beats: list[float]
    # Global estimate over the whole track — a separate, coarser signal
    # from each candidate's own local_key above. Null when the harmonic
    # signal is too weak/ambiguous to trust (never a guessed value).
    estimated_key: PitchClass | None = None
    estimated_mode: Mode | None = None
    key_confidence: float = Field(default=0.0, ge=0, le=1)
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
    # "smooth" (default) is the original M7 full-band crossfade, unchanged.
    # "bass_swap" additionally narrows bass ownership around
    # bass_swap_position — see services/transition_renderer.py.
    transition_style: TransitionStyle = "smooth"
    bass_swap_position: float = Field(default=0.5, ge=0.0, le=1.0)
    bass_swap_width_beats: BassSwapWidthBeats = 4

    @field_validator("song_a_bpm", "song_b_bpm")
    @classmethod
    def _finite_positive_bpm(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("bpm must be a finite, positive number")
        return value

    @model_validator(mode="after")
    def _validate_bass_swap_fits_transition(self) -> TransitionRenderRequest:
        # Bass-specific fields are only meaningful (and only validated)
        # when transition_style actually uses them — a smooth request
        # doesn't need a valid bass-swap window at all.
        if self.transition_style != "bass_swap":
            return self
        low, high = _valid_bass_swap_range(
            self.transition_beats, self.bass_swap_width_beats
        )
        if not (low <= self.bass_swap_position <= high):
            raise ValueError(
                f"bass_swap_position must be between {low:.4f} and "
                f"{high:.4f} for a {self.bass_swap_width_beats}-beat swap "
                f"within a {self.transition_beats}-beat transition"
            )
        return self


class SuggestedAnchor(BaseModel):
    beat_index: int = Field(..., ge=0)
    time_seconds: float = Field(..., ge=0)


class TransitionSuggestion(BaseModel):
    """Shaped to drop directly into the frontend's TransitionPlan — the
    manual editor and the suggestion flow share one plan representation.
    Also reused, unmodified, as each TransitionVariant's `plan` below."""

    song_a_anchor: SuggestedAnchor
    song_b_anchor: SuggestedAnchor
    transition_beats: Literal[8, 16, 32]
    song_a_gain_db: float
    song_b_gain_db: float
    crossfade_bias: float
    song_b_tempo_multiplier: Literal[0.5, 1.0, 2.0]
    transition_style: TransitionStyle = "smooth"
    bass_swap_position: float = Field(default=0.5, ge=0.0, le=1.0)
    bass_swap_width_beats: BassSwapWidthBeats = 4


class TransitionChoice(BaseModel):
    """One deterministic, distinct Song A exit / Song B entry anchor PAIR
    the planner judged compatible (M12's pairwise search) — see
    services/transition_planner.suggest_transition_choices. Choices differ
    in WHICH anchors are used, not merely in presentation: each carries its
    own ready-to-adopt `plan` plus the local harmonic context and
    compatibility summary specific to that pair.

    `compatibility` and `harmonic_compatibility` are both in [0, 1] and
    measure deterministic, documented feature agreement (tempo, harmony,
    structure, energy continuity, timbre, rhythm) — never a claim about
    how a transition will actually sound, and never the only thing a user
    should rely on to choose between options (auditioning via Preview is
    the real check)."""

    id: str
    label: str
    description: str
    plan: TransitionSuggestion
    compatibility: float = Field(..., ge=0, le=1)
    # Local harmonic context around THIS choice's specific anchors — not
    # the tracks' global estimated_key. Neutral (0.5) / null whenever
    # reliable local harmony wasn't available for either anchor.
    harmonic_compatibility: float = Field(..., ge=0, le=1)
    song_a_local_key: PitchClass | None = None
    song_a_local_mode: Mode | None = None
    song_b_local_key: PitchClass | None = None
    song_b_local_mode: Mode | None = None


class TransitionSuggestRequest(BaseModel):
    """Takes the two already-computed analyses directly — suggesting a
    plan needs no raw audio, so this never re-uploads either file."""

    song_a_analysis: TrackAnalysis
    song_b_analysis: TrackAnalysis


class TransitionSuggestResponse(BaseModel):
    """Up to MAX_CHOICES distinct anchor-pair choices (see
    services/transition_planner), ranked best-first — `choices[0]` is the
    single best pairing found. Tempo interpretation is a property of the
    two tracks' overall BPMs, not of any one anchor pair, so it's reported
    once here rather than repeated per choice."""

    choices: list[TransitionChoice] = Field(..., min_length=1)
    effective_song_b_bpm: float = Field(..., gt=0)
    tempo_compatibility: Literal["compatible", "moderate", "significant", "extreme"]
    used_tempo_normalization: bool
    song_a_anchor_source: Literal["candidate", "fallback"]
    song_b_anchor_source: Literal["candidate", "fallback"]
