"""Deterministic transition-plan suggestion from two already-analyzed
tracks.

track analysis (TrackAnalysis, incl. entry/exit candidates + local key)
   -> this planner (pairwise candidate-PAIR search + M6 tempo/length/gain)
   -> up to MAX_CHOICES distinct TransitionChoice suggestions
   -> the existing manual editor / renderer, entirely unchanged

No LLM, no randomness: every decision here is a plain function of the two
TrackAnalysis inputs, so the same two analyses always produce the same
choices in the same order.

--- M12: pairwise search -----------------------------------------------
Earlier milestones (M6-M9) picked Song A's best-scoring exit candidate and
Song B's best-scoring entry candidate mostly independently (M9 already
scored pairs jointly for HARMONY specifically — see the now-superseded
_choose_best_candidate_pair this replaces). A good exit point is not
necessarily compatible with every good entry point: two songs can each
have a strong candidate individually while making a poor PAIR together
(clashing key, a jarring loudness jump, wildly different local timbre).

M12 instead scores every (exit, entry) pair from two bounded candidate
pools (see audio_analysis.MAX_CANDIDATES_PER_ROLE, currently 24 per role)
with one deterministic compatibility formula (see _pair_score), then
returns up to MAX_CHOICES of the best pairs, filtered so they represent
genuinely different anchor pairs rather than near-duplicates a few beats
apart (see _select_diverse_pairs). With <=24 candidates per role, that's
<=576 pair scores — all plain arithmetic on already-computed features, no
audio decoding, comfortably bounded for a live request.

Known limitation (see PROJECT/CLAUDE.md and the M12 report): none of this
reasons about bars, phrases, downbeats, or song sections — only about
individual detected beats and the analysis features already computed at
each one. A pair can land in the middle of a phrase as easily as at its
start; see audio_analysis.py's own beat-detection docstring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.schemas import TrackAnalysis, TransitionCandidate
from app.services.harmonic_compatibility import (
    NEUTRAL_COMPATIBILITY,
    harmonic_compatibility,
)

# Deterministic fallback positions (fraction of track duration), used only
# when a track has no eligible candidate for its role at all.
SONG_A_FALLBACK_POSITION = 0.75
SONG_B_FALLBACK_POSITION = 0.15

# How many distinct anchor-pair choices to return (when the candidate pools
# allow it — see suggest_transition_choices).
MAX_CHOICES = 3

# --- Pairwise candidate-pair scoring (M12) --------------------------------
# pair_score = EXIT_QUALITY_WEIGHT   * song_a_candidate.score
#            + ENTRY_QUALITY_WEIGHT  * song_b_candidate.score
#            + TEMPO_WEIGHT          * tempo_compatibility_term
#            + HARMONY_WEIGHT        * harmonic_compatibility(...)
#            + ENERGY_WEIGHT         * energy_continuity_score(...)
#            + TIMBRE_WEIGHT         * timbral_compatibility_score(...)
#            + RHYTHM_WEIGHT         * rhythmic_compatibility_score(...)
#
# Every term is already normalized to [0, 1] (candidate.score is min-max
# normalized across its own role's eligible pool by audio_analysis.py; the
# rest are constructed to [0, 1] below), and the weights sum to exactly
# 1.0, so `pair_score` itself is always in [0, 1] — no extra rescaling
# needed to report it as TransitionChoice.compatibility.
#
# This is a deterministic, documented FEATURE-AGREEMENT score, not a
# measurement of how a transition will actually sound. It never claims to
# find "the objectively smoothest" transition (see the M12 spec) — it
# ranks pairs by how well several independently-reasoned signals agree,
# so users can audition a short, meaningfully different list instead of
# every possible beat combination.
#
# Weights, in descending order of trust:
#   - EXIT/ENTRY quality (0.22 each, 0.44 combined) carry the most weight:
#     each candidate's own score already blends structural change,
#     boundary strength, energy change, and position (see
#     audio_analysis.WEIGHT_*) — the richest single signal available.
#   - TEMPO (0.15) and HARMONY (0.15): both well-established, confidently
#     computed signals (tempo from actual detected BPMs; harmony from
#     documented key-relationship theory), but neither alone determines
#     whether two specific beats splice well.
#   - ENERGY CONTINUITY (0.14): comparable in importance to tempo/harmony
#     — an abrupt loudness jump is immediately audible — but M6's gain
#     suggestion already partly compensates for it, so its OWN weight here
#     is calibrated relative to what that compensation can't fix (see
#     _energy_continuity_score).
#   - TIMBRE (0.07) and RHYTHM (0.05) are deliberately the smallest
#     weights: per the M12 spec, "stylistically different songs can still
#     transition well" and an onset-density mismatch is a soft, coarse
#     signal — these should be able to break a near-tie, never dominate.
EXIT_QUALITY_WEIGHT = 0.22
ENTRY_QUALITY_WEIGHT = 0.22
TEMPO_WEIGHT = 0.15
HARMONY_WEIGHT = 0.15
ENERGY_CONTINUITY_WEIGHT = 0.14
TIMBRAL_WEIGHT = 0.07
RHYTHMIC_WEIGHT = 0.05
assert (
    round(
        EXIT_QUALITY_WEIGHT
        + ENTRY_QUALITY_WEIGHT
        + TEMPO_WEIGHT
        + HARMONY_WEIGHT
        + ENERGY_CONTINUITY_WEIGHT
        + TIMBRAL_WEIGHT
        + RHYTHMIC_WEIGHT,
        6,
    )
    == 1.0
)

# --- Diversity filtering (M12) --------------------------------------------
# Two pairs are treated as near-duplicates (and so shouldn't both consume a
# choice slot) only when BOTH anchors sit within this many beats of an
# already-chosen pair's anchors — e.g. a pair one neighboring beat away on
# both sides. A pair that differs meaningfully on EITHER side (a
# structurally different moment in at least one track) still counts as
# distinct, since it represents a genuinely different musical choice even
# if the other track's anchor happens to repeat.
DIVERSITY_MIN_BEAT_GAP = 3

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

# The pairwise TEMPO term decays linearly from 1.0 (perfect match) to 0.0
# at this change magnitude — chosen to match TEMPO_CHANGE_EXTREME so the
# continuous pairwise term and the existing discrete tempo_compatibility
# category reach "no further credit" at the same point.
TEMPO_TERM_ZERO_AT = TEMPO_CHANGE_EXTREME

# clamp bound for the approximate Song B level-matching suggestion.
GAIN_MATCH_LIMIT_DB = 6.0

# The energy-continuity term (see _energy_continuity_score) stays at 1.0
# for any loudness gap the existing gain suggestion can already absorb
# (+-GAIN_MATCH_LIMIT_DB), then decays linearly to 0.0 over this many
# additional dB of *residual* gap — a gap gain trimming can't fix is a
# genuinely more abrupt jump, not just a mixing-level choice.
ENERGY_CONTINUITY_DB_RANGE = 18.0

# Cosine similarity of two local MFCC vectors already lands in [-1, 1];
# NEUTRAL_TIMBRAL_COMPATIBILITY is used only when one/both candidates
# lack MFCC data (short/atypical audio) rather than penalizing missing
# data, mirroring NEUTRAL_COMPATIBILITY's role for harmony.
NEUTRAL_TIMBRAL_COMPATIBILITY = 0.5


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
    local_key: str | None = None
    local_mode: str | None = None
    local_key_confidence: float = 0.0


@dataclass(frozen=True)
class TransitionChoice:
    """One distinct, ready-to-adopt anchor-pair suggestion — see the
    module docstring. `transition_style` is always "smooth" here: M12
    intentionally does not auto-vary transition technique per choice (see
    the module docstring's style/length note); the existing editor's own
    Smooth/Bass Swap toggle still works unchanged once a choice is
    adopted."""

    id: str
    label: str
    description: str
    song_a_anchor: AnchorChoice
    song_b_anchor: AnchorChoice
    transition_beats: int
    song_a_gain_db: float
    song_b_gain_db: float
    crossfade_bias: float
    song_b_tempo_multiplier: float
    transition_style: str
    bass_swap_position: float
    bass_swap_width_beats: int
    compatibility: float
    harmonic_compatibility: float


@dataclass(frozen=True)
class TransitionChoicesResult:
    choices: list[TransitionChoice]
    effective_song_b_bpm: float
    tempo_compatibility: str
    used_tempo_normalization: bool
    song_a_anchor_source: str  # "candidate" | "fallback"
    song_b_anchor_source: str  # "candidate" | "fallback"


# Neutral, deterministic rank-based copy — see the M12 spec's explicit
# language guidance: never claim "objectively smoothest," and don't expose
# a raw numeric score as the primary UX (auditioning via Preview is).
_CHOICE_LABELS: tuple[str, ...] = (
    "Suggested transition",
    "Alternative transition",
    "Another alternative",
)
_CHOICE_DESCRIPTIONS: tuple[str, ...] = (
    "Ranked highest for tempo, harmony, and energy compatibility.",
    "A different exit and entry point pairing worth comparing.",
    "A different exit and entry point pairing worth comparing.",
)


def suggest_transition_choices(
    song_a_analysis: TrackAnalysis, song_b_analysis: TrackAnalysis
) -> TransitionChoicesResult:
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
    tempo_term = _tempo_compatibility_term(change_magnitude)

    pairs, song_a_source, song_b_source = _choose_anchor_pairs(
        song_a_analysis, song_b_analysis, tempo_term
    )

    choices = [
        _build_choice(index, pair, transition_beats, multiplier)
        for index, pair in enumerate(pairs)
    ]

    return TransitionChoicesResult(
        choices=choices,
        effective_song_b_bpm=effective_song_b_bpm,
        tempo_compatibility=tempo_compatibility,
        used_tempo_normalization=multiplier != 1.0,
        song_a_anchor_source=song_a_source,
        song_b_anchor_source=song_b_source,
    )


def _build_choice(
    index: int,
    pair: _ScoredPair,
    transition_beats: int,
    multiplier: float,
) -> TransitionChoice:
    song_a_anchor = _anchor_from_candidate(pair.exit_candidate)
    song_b_anchor = _anchor_from_candidate(pair.entry_candidate)
    song_a_gain_db, song_b_gain_db = _suggest_gains(song_a_anchor, song_b_anchor)
    label_index = min(index, len(_CHOICE_LABELS) - 1)

    return TransitionChoice(
        id=str(index + 1),
        label=_CHOICE_LABELS[label_index],
        description=_CHOICE_DESCRIPTIONS[label_index],
        song_a_anchor=song_a_anchor,
        song_b_anchor=song_b_anchor,
        transition_beats=transition_beats,
        song_a_gain_db=song_a_gain_db,
        song_b_gain_db=song_b_gain_db,
        crossfade_bias=0.0,
        song_b_tempo_multiplier=multiplier,
        transition_style="smooth",
        bass_swap_position=0.5,
        bass_swap_width_beats=BASS_SWAP_WIDTH_BY_TRANSITION_BEATS[transition_beats],
        compatibility=round(pair.score, 4),
        harmonic_compatibility=round(pair.harmonic_compatibility, 4),
    )


def _choose_anchor_pairs(
    song_a_analysis: TrackAnalysis,
    song_b_analysis: TrackAnalysis,
    tempo_term: float,
) -> tuple[list[_ScoredPair], str, str]:
    """Returns up to MAX_CHOICES scored (exit, entry) pairs, best first,
    plus each side's anchor source ("candidate" | "fallback").

    When both roles have real candidates, every pair from the two bounded
    pools is scored jointly (see _rank_candidate_pairs) and then filtered
    for diversity (see _select_diverse_pairs) — this is the M12 pairwise
    search. When either side has NO candidates at all, there is only one
    possible anchor for that side (M6's deterministic nearest-beat
    fallback), so at most one meaningful pair exists; that single pair is
    still scored with the SAME formula (see _candidate_like_from_anchor)
    for a consistent `compatibility` value, just with reduced signal on
    whichever side has no real candidate data."""
    exit_candidates = song_a_analysis.exit_candidates
    entry_candidates = song_b_analysis.entry_candidates

    if exit_candidates and entry_candidates:
        scored = _rank_candidate_pairs(exit_candidates, entry_candidates, tempo_term)
        selected = _select_diverse_pairs(scored, MAX_CHOICES)
        return selected, "candidate", "candidate"

    song_a_anchor = _choose_anchor_independent(
        exit_candidates,
        song_a_analysis.beats,
        song_a_analysis.duration_seconds,
        SONG_A_FALLBACK_POSITION,
    )
    song_b_anchor = _choose_anchor_independent(
        entry_candidates,
        song_b_analysis.beats,
        song_b_analysis.duration_seconds,
        SONG_B_FALLBACK_POSITION,
    )
    exit_like = _candidate_like_from_anchor(song_a_anchor)
    entry_like = _candidate_like_from_anchor(song_b_anchor)
    pair = _score_pair(exit_like, entry_like, tempo_term)
    return (
        [pair],
        "candidate" if exit_candidates else "fallback",
        "candidate" if entry_candidates else "fallback",
    )


# --- Pairwise scoring ------------------------------------------------------


@dataclass(frozen=True)
class _ScoredPair:
    exit_candidate: TransitionCandidate
    entry_candidate: TransitionCandidate
    score: float
    harmonic_compatibility: float


def _rank_candidate_pairs(
    exit_candidates: list[TransitionCandidate],
    entry_candidates: list[TransitionCandidate],
    tempo_term: float,
) -> list[_ScoredPair]:
    """Every (exit, entry) pair, scored and sorted best-first. Bounded by
    audio_analysis.MAX_CANDIDATES_PER_ROLE on each side (currently 24), so
    this is at most 576 pair scores — plain arithmetic on already-computed
    features, not audio decoding."""
    pairs = [
        _score_pair(exit_candidate, entry_candidate, tempo_term)
        for exit_candidate in exit_candidates
        for entry_candidate in entry_candidates
    ]
    pairs.sort(key=lambda pair: pair.score, reverse=True)
    return pairs


def _score_pair(
    exit_candidate: TransitionCandidate,
    entry_candidate: TransitionCandidate,
    tempo_term: float,
) -> _ScoredPair:
    harmony = harmonic_compatibility(
        exit_candidate.local_key,
        exit_candidate.local_mode,
        entry_candidate.local_key,
        entry_candidate.local_mode,
    )
    energy = _energy_continuity_score(exit_candidate, entry_candidate)
    timbre = _timbral_compatibility_score(exit_candidate, entry_candidate)
    rhythm = _rhythmic_compatibility_score(exit_candidate, entry_candidate)

    score = (
        EXIT_QUALITY_WEIGHT * exit_candidate.score
        + ENTRY_QUALITY_WEIGHT * entry_candidate.score
        + TEMPO_WEIGHT * tempo_term
        + HARMONY_WEIGHT * harmony
        + ENERGY_CONTINUITY_WEIGHT * energy
        + TIMBRAL_WEIGHT * timbre
        + RHYTHMIC_WEIGHT * rhythm
    )
    return _ScoredPair(
        exit_candidate=exit_candidate,
        entry_candidate=entry_candidate,
        score=score,
        harmonic_compatibility=harmony,
    )


def _tempo_compatibility_term(change_magnitude: float) -> float:
    """Continuous [0, 1] counterpart to _choose_length_and_compatibility's
    discrete category, for use inside the pairwise score. 1.0 at a perfect
    match, decaying linearly to 0.0 at TEMPO_TERM_ZERO_AT (== the existing
    "extreme" threshold) — reuses the same _tempo_change_magnitude every
    other tempo decision in this module already uses, never a separate
    tempo calculation."""
    return _clamp01(1.0 - change_magnitude / TEMPO_TERM_ZERO_AT)


def _energy_continuity_score(
    exit_candidate: TransitionCandidate, entry_candidate: TransitionCandidate
) -> float:
    """1.0 when the exit and entry sit at a loudness gap the existing gain
    suggestion can already absorb (see _suggest_gains's
    GAIN_MATCH_LIMIT_DB); decays to 0.0 as the RESIDUAL gap (beyond what a
    +-6 dB trim can fix) grows toward ENERGY_CONTINUITY_DB_RANGE. Reuses
    energy_before/energy_after exactly as _suggest_gains does — never
    decodes audio. Neutral when either side has no real energy reading."""
    if exit_candidate.energy_before <= 0 or entry_candidate.energy_after <= 0:
        return NEUTRAL_COMPATIBILITY
    gap_db = abs(
        _rms_to_db(exit_candidate.energy_before)
        - _rms_to_db(entry_candidate.energy_after)
    )
    residual_db = max(0.0, gap_db - GAIN_MATCH_LIMIT_DB)
    return _clamp01(1.0 - residual_db / ENERGY_CONTINUITY_DB_RANGE)


def _timbral_compatibility_score(
    exit_candidate: TransitionCandidate, entry_candidate: TransitionCandidate
) -> float:
    """Cosine similarity between the two candidates' local MFCC summaries
    (see audio_analysis._local_timbre_at), rescaled from [-1, 1] to
    [0, 1]. A coarse, DELIBERATELY LOW-WEIGHT signal (see TIMBRAL_WEIGHT):
    stylistically different songs can still transition well, so this only
    breaks near-ties, never dominates. Neutral when either side lacks MFCC
    data (harmonic feature extraction failed for that track)."""
    if not exit_candidate.local_timbre or not entry_candidate.local_timbre:
        return NEUTRAL_TIMBRAL_COMPATIBILITY
    similarity = _cosine_similarity(
        exit_candidate.local_timbre, entry_candidate.local_timbre
    )
    if similarity is None:
        return NEUTRAL_TIMBRAL_COMPATIBILITY
    return _clamp01((similarity + 1.0) / 2.0)


def _rhythmic_compatibility_score(
    exit_candidate: TransitionCandidate, entry_candidate: TransitionCandidate
) -> float:
    """A coarse onset-DENSITY agreement check: how close the two
    candidates' boundary_strength (local onset activity) values are,
    RELATIVE to their combined magnitude — 1.0 when equal, falling toward
    0.0 as one side is far busier than the other. Relative (not absolute)
    on purpose: boundary_strength's scale depends on each track's own
    mix/loudness, so only the two candidates' PROPORTION to each other is
    comparable across tracks. Neutral when both sides are silent/near-zero
    (nothing to compare)."""
    a = exit_candidate.boundary_strength
    b = entry_candidate.boundary_strength
    total = a + b
    if total <= 1e-9:
        return NEUTRAL_COMPATIBILITY
    return _clamp01(1.0 - abs(a - b) / total)


def _cosine_similarity(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 1e-9 or norm_b <= 1e-9:
        return None
    similarity = dot / (norm_a * norm_b)
    return min(max(similarity, -1.0), 1.0)  # guard fp drift


def _candidate_like_from_anchor(anchor: AnchorChoice) -> TransitionCandidate:
    """Adapts a fallback/independent AnchorChoice (no ranked-candidate data
    at all) into a TransitionCandidate shape so the SAME _score_pair
    formula can score it — rather than a second, parallel scoring formula.
    `score` and `boundary_strength` use neutral defaults (no structural
    ranking exists for a fallback position); every sub-score already
    degrades gracefully to NEUTRAL when its own inputs are missing."""
    return TransitionCandidate(
        beat_index=anchor.beat_index,
        time_seconds=anchor.time_seconds,
        score=NEUTRAL_COMPATIBILITY,
        boundary_strength=0.0,
        energy_before=anchor.energy_before or 0.0,
        energy_after=anchor.energy_after or 0.0,
        structure_strength=0.0,
        local_key=anchor.local_key,
        local_mode=anchor.local_mode,
        local_key_confidence=anchor.local_key_confidence,
        local_timbre=None,
    )


# --- Diversity filtering ----------------------------------------------------


def _select_diverse_pairs(
    scored_pairs: list[_ScoredPair], target: int
) -> list[_ScoredPair]:
    """Greedily takes the best-scoring pair, then walks down the
    (already-sorted) list adding the next pair only if it's distinct (see
    _is_distinct_pair) from every pair already chosen — deterministic, no
    randomness. If the candidate pool is small/sparse enough that fewer
    than `target` mutually-distinct pairs exist, backfills with the
    remaining best-scoring pairs so the caller still gets up to `target`
    choices rather than fewer whenever that many pairs exist at all."""
    chosen: list[_ScoredPair] = []
    for pair in scored_pairs:
        if all(_is_distinct_pair(pair, existing) for existing in chosen):
            chosen.append(pair)
        if len(chosen) == target:
            return chosen

    for pair in scored_pairs:
        if len(chosen) == target:
            break
        if pair not in chosen:
            chosen.append(pair)
    return chosen


def _is_distinct_pair(a: _ScoredPair, b: _ScoredPair) -> bool:
    exit_gap = abs(a.exit_candidate.beat_index - b.exit_candidate.beat_index)
    entry_gap = abs(a.entry_candidate.beat_index - b.entry_candidate.beat_index)
    return exit_gap >= DIVERSITY_MIN_BEAT_GAP or entry_gap >= DIVERSITY_MIN_BEAT_GAP


# --- Shared helpers (anchors, tempo, gain) ---------------------------------


def _anchor_from_candidate(candidate: TransitionCandidate) -> AnchorChoice:
    return AnchorChoice(
        beat_index=candidate.beat_index,
        time_seconds=candidate.time_seconds,
        energy_before=candidate.energy_before,
        energy_after=candidate.energy_after,
        from_candidate=True,
        local_key=candidate.local_key,
        local_mode=candidate.local_mode,
        local_key_confidence=candidate.local_key_confidence,
    )


def _choose_anchor_independent(
    candidates: list[TransitionCandidate],
    beats: list[float],
    duration_seconds: float,
    fallback_position: float,
) -> AnchorChoice:
    if candidates:
        best = max(candidates, key=lambda candidate: candidate.score)
        return _anchor_from_candidate(best)

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


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)


# --- Style/length policy ----------------------------------------------------
# Deterministic policy: the bass-swap width every choice's plan would use
# if the user manually switches to Bass Swap in the editor — always one
# quarter of the transition length. Since transition_beats is always one
# of {8, 16, 32} (the render request's supported lengths), this always
# lands exactly on one of the three valid BassSwapWidthBeats values
# {2, 4, 8} — no clamping or rounding ever needed, and the resulting
# half-width (see transition_renderer._valid_bass_swap_range) is always
# exactly 0.125, comfortably inside the valid range for
# bass_swap_position = 0.5. Every TransitionChoice carries a ready
# bass_swap_width_beats for this reason even though its own
# transition_style defaults to "smooth" (see the module docstring).
BASS_SWAP_WIDTH_BY_TRANSITION_BEATS: dict[int, int] = {8: 2, 16: 4, 32: 8}
