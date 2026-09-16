"""Deterministic transition-plan suggestion from two already-analyzed
tracks.

track analysis (TrackAnalysis, incl. entry/exit candidates)
   -> this planner
   -> a TransitionPlan-shaped suggestion
   -> the existing manual editor / renderer, entirely unchanged

No LLM, no randomness: every decision here is a plain function of the two
TrackAnalysis inputs, so the same two analyses always produce the same
suggestion.
"""

import math
from dataclasses import dataclass

from app.schemas import TrackAnalysis, TransitionCandidate

# Deterministic fallback positions (fraction of track duration), used only
# when a track has no eligible candidate for its role at all.
SONG_A_FALLBACK_POSITION = 0.75
SONG_B_FALLBACK_POSITION = 0.15

# Reasonable equivalent tempo interpretations for Song B relative to its
# raw analyzed BPM — tempo trackers sometimes report the same pulse at
# half or double speed. We never overwrite the raw BPM; this only scales
# what the *renderer* treats as Song B's tempo.
TEMPO_MULTIPLIER_CANDIDATES: tuple[float, ...] = (0.5, 1.0, 2.0)

# Thresholds on abs(log(song_a_bpm / effective_song_b_bpm)) — a symmetric
# measure of tempo-change magnitude (speed-up and slow-down alike) after
# choosing the best half/double-time interpretation. Roughly:
#   0.05 ~= a 5% stretch     0.15 ~= a 16% stretch     0.30 ~= a 35% stretch
# Kept as one named block rather than scattered magic numbers.
#
# Note: with candidates {0.5, 1, 2}, the worst possible *best-case* distance
# (the true ratio sitting exactly between two adjacent candidates, e.g.
# sqrt(2) away from both 1x and 2x) is ln(2)/2 ~= 0.3466 — so EXTREME must
# stay below that or it could never actually trigger.
TEMPO_CHANGE_COMPATIBLE = 0.05
TEMPO_CHANGE_MODERATE = 0.15
TEMPO_CHANGE_EXTREME = 0.30

# clamp bound for the approximate Song B level-matching suggestion.
GAIN_MATCH_LIMIT_DB = 6.0


class TransitionPlannerError(Exception):
    """Raised when a transition plan cannot be suggested from the given
    analyses (e.g. a track has no detected beats at all)."""


@dataclass(frozen=True)
class AnchorChoice:
    beat_index: int
    time_seconds: float
    energy_before: float | None
    energy_after: float | None
    from_candidate: bool


@dataclass(frozen=True)
class TransitionSuggestionResult:
    song_a_anchor: AnchorChoice
    song_b_anchor: AnchorChoice
    transition_beats: int
    song_a_gain_db: float
    song_b_gain_db: float
    crossfade_bias: float
    song_b_tempo_multiplier: float
    effective_song_b_bpm: float
    tempo_compatibility: str


def suggest_transition_plan(
    song_a_analysis: TrackAnalysis, song_b_analysis: TrackAnalysis
) -> TransitionSuggestionResult:
    song_a_anchor = _choose_anchor(
        song_a_analysis.exit_candidates,
        song_a_analysis.beats,
        song_a_analysis.duration_seconds,
        SONG_A_FALLBACK_POSITION,
    )
    song_b_anchor = _choose_anchor(
        song_b_analysis.entry_candidates,
        song_b_analysis.beats,
        song_b_analysis.duration_seconds,
        SONG_B_FALLBACK_POSITION,
    )

    multiplier = _choose_tempo_multiplier(
        song_a_analysis.tempo_bpm, song_b_analysis.tempo_bpm
    )
    effective_song_b_bpm = song_b_analysis.tempo_bpm * multiplier
    change_magnitude = _tempo_change_magnitude(
        song_a_analysis.tempo_bpm, effective_song_b_bpm
    )

    transition_beats, tempo_compatibility = _choose_length_and_compatibility(
        change_magnitude
    )

    song_a_gain_db, song_b_gain_db = _suggest_gains(song_a_anchor, song_b_anchor)

    return TransitionSuggestionResult(
        song_a_anchor=song_a_anchor,
        song_b_anchor=song_b_anchor,
        transition_beats=transition_beats,
        song_a_gain_db=song_a_gain_db,
        song_b_gain_db=song_b_gain_db,
        crossfade_bias=0.0,
        song_b_tempo_multiplier=multiplier,
        effective_song_b_bpm=effective_song_b_bpm,
        tempo_compatibility=tempo_compatibility,
    )


def _choose_anchor(
    candidates: list[TransitionCandidate],
    beats: list[float],
    duration_seconds: float,
    fallback_position: float,
) -> AnchorChoice:
    if candidates:
        best = max(candidates, key=lambda candidate: candidate.score)
        return AnchorChoice(
            beat_index=best.beat_index,
            time_seconds=best.time_seconds,
            energy_before=best.energy_before,
            energy_after=best.energy_after,
            from_candidate=True,
        )

    beat_index = _nearest_beat_index(beats, fallback_position * duration_seconds)
    return AnchorChoice(
        beat_index=beat_index,
        time_seconds=beats[beat_index],
        energy_before=None,
        energy_after=None,
        from_candidate=False,
    )


def _nearest_beat_index(beats: list[float], target_seconds: float) -> int:
    if not beats:
        raise TransitionPlannerError(
            "Track has no detected beats to suggest an anchor from."
        )
    return min(range(len(beats)), key=lambda i: abs(beats[i] - target_seconds))


def _choose_tempo_multiplier(song_a_bpm: float, song_b_bpm: float) -> float:
    if (
        not math.isfinite(song_a_bpm)
        or not math.isfinite(song_b_bpm)
        or song_a_bpm <= 0
        or song_b_bpm <= 0
    ):
        raise TransitionPlannerError(
            "Both tracks need a valid detected BPM to suggest a transition."
        )
    return min(
        TEMPO_MULTIPLIER_CANDIDATES,
        key=lambda multiplier: _tempo_change_magnitude(
            song_a_bpm, song_b_bpm * multiplier
        ),
    )


def _tempo_change_magnitude(song_a_bpm: float, effective_song_b_bpm: float) -> float:
    return abs(math.log(song_a_bpm / effective_song_b_bpm))


def _choose_length_and_compatibility(change_magnitude: float) -> tuple[int, str]:
    if change_magnitude <= TEMPO_CHANGE_COMPATIBLE:
        return 32, "compatible"
    if change_magnitude <= TEMPO_CHANGE_MODERATE:
        return 16, "moderate"
    if change_magnitude <= TEMPO_CHANGE_EXTREME:
        return 8, "significant"
    return 8, "extreme"


def _suggest_gains(
    song_a_anchor: AnchorChoice, song_b_anchor: AnchorChoice
) -> tuple[float, float]:
    """Song A always stays at 0 dB. Song B gets a modest nudge toward Song
    A's local level only when both anchors came from real candidate data
    (i.e. real RMS readings, not the position-only fallback)."""
    if (
        song_a_anchor.energy_before is None
        or song_b_anchor.energy_after is None
        or song_a_anchor.energy_before <= 0
        or song_b_anchor.energy_after <= 0
    ):
        return 0.0, 0.0

    song_a_local_db = _rms_to_db(song_a_anchor.energy_before)
    song_b_local_db = _rms_to_db(song_b_anchor.energy_after)

    song_b_gain_db = _clamp(
        song_a_local_db - song_b_local_db, -GAIN_MATCH_LIMIT_DB, GAIN_MATCH_LIMIT_DB
    )
    return 0.0, song_b_gain_db


def _rms_to_db(rms: float, floor: float = 1e-6) -> float:
    return 20.0 * math.log10(max(rms, floor))


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
