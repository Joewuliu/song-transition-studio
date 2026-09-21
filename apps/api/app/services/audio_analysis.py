"""Musical analysis (tempo/beats/candidates/key) for uploaded audio,
backed by librosa.

Uploaded audio is never kept: each call writes the given bytes to a private
temporary file (librosa/soundfile need a real path for some codecs), decodes
it, and removes the file again before returning.
"""

import math
import os
import tempfile
from dataclasses import dataclass

import librosa
import numpy as np

from app.schemas import TrackAnalysis, TransitionCandidate
from app.services.upload_validation import safe_temp_suffix

HOP_LENGTH = 512

# Beats of context averaged on each side of a candidate beat for the
# short-term energy/onset signal — smoothing/context only, *not* a bar or
# measure (no 4/4 assumption).
CANDIDATE_CONTEXT_BEATS = 2

# Longer-term musical context compared on each side of a beat for
# structural-change detection. Wider than CANDIDATE_CONTEXT_BEATS on
# purpose — this is meant to catch a genuine shift in the surrounding
# passage, not a single transient. Still just "context," never a bar
# or phrase.
STRUCTURE_CONTEXT_BEATS = 8

# Context on each side used for a candidate's own *local* key/mode
# estimate. Tighter than STRUCTURE_CONTEXT_BEATS since this should reflect
# the harmony right around the splice point, not a wider passage.
LOCAL_KEY_CONTEXT_BEATS = 4

# Cap on how many ranked candidates are returned per role — small
# shortlists, not the full per-frame feature data. Raised from M6/M7's 10
# for M12: the planner now searches PAIRS of (Song A exit, Song B entry)
# candidates jointly (see services/transition_planner.py), and a wider
# pool per role gives that search more genuinely distinct musical material
# to choose from. 24x24 = 576 pairs worst case — still trivial to score
# in full (see the planner's own module docstring for the bound).
MAX_CANDIDATES_PER_ROLE = 24

# Track-position eligibility windows (fraction of duration) for each role.
# Position is only ONE scoring input (see _rank_candidates); these ranges
# just exclude positions that could never be a sensible transition point
# (e.g. right at the very start/end, where too little audio would remain).
SONG_A_EXIT_POSITION_RANGE = (0.55, 0.92)
SONG_B_ENTRY_POSITION_RANGE = (0.03, 0.45)

# Where each range's score peaks — matches the planner's deterministic
# fallback positions one-for-one, so "no strong candidate found" and
# "candidate found but position-neutral" land in the same neighborhood.
SONG_A_EXIT_PREFERRED_POSITION = 0.75
SONG_B_ENTRY_PREFERRED_POSITION = 0.15

# --- Candidate scoring weights -------------------------------------------
# score = WEIGHT_STRUCTURE          * normalized(structure_strength)
#       + WEIGHT_BOUNDARY_STRENGTH  * normalized(boundary_strength)
#       + WEIGHT_ENERGY_CHANGE      * normalized(energy_change)
#       + WEIGHT_POSITION           * normalized(1 - |position - preferred|)
# normalized() min-max scales across the eligible candidates for that role
# (see _normalize) — a *relative* comparison, not an absolute one.
#
# Revisited from M6 (which only had boundary/energy/position at
# 0.5/0.3/0.2): structural change is a longer-context, more meaningful
# signal than short-term onset activity alone, so it now carries the
# largest weight. Position is reduced to the smallest weight — one signal
# among several, never the primary driver.
WEIGHT_STRUCTURE = 0.40
WEIGHT_BOUNDARY_STRENGTH = 0.25
WEIGHT_ENERGY_CHANGE = 0.20
WEIGHT_POSITION = 0.15

# --- Global/local key estimation ------------------------------------------
# Krumhansl-Kessler key profiles: the classic, widely-published templates
# for how strongly each pitch class (relative to the tonic) is expected to
# appear in a major/minor key. Correlating an aggregated chroma vector
# against every rotation of these profiles is the standard
# Krumhansl-Schmuckler key-finding method.
PITCH_CLASSES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)
KRUMHANSL_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
KRUMHANSL_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)

# Confidence combines two things (see _estimate_key for the exact formula):
# how strong the winning profile's correlation is on its own, AND how
# clearly it beats the second-best of all 24 candidates (12 pitch classes x
# major/minor). A track that correlates almost equally well with two
# different keys (e.g. a key and its relative major/minor) is genuinely
# more ambiguous than one with a clear, isolated winner, even if the raw
# best correlation is the same in both cases. Below this, the key is
# reported as unknown (null) rather than inventing certainty.
KEY_CONFIDENCE_MINIMUM = 0.55

# Correlation margin (best minus second-best) at/above which the margin
# component of confidence is treated as maximally confident. 0.2 is a
# fairly modest gap on the Pearson correlation's [-1, 1] scale — chosen
# from observing that a clear, isolated single-chord signal reliably beats
# its next-best (usually the relative major/minor) by at least this much,
# while a genuinely ambiguous/dual-key signal sits within ~0.01 of it.
KEY_MARGIN_SCALE = 0.2


class AudioAnalysisError(Exception):
    """Raised when uploaded audio cannot be decoded or analyzed."""


@dataclass
class _TrackFeatures:
    """Shared per-frame features, computed once per track and reused for
    global key estimation, candidate structural scoring, and each
    candidate's local harmonic context — never recomputed per candidate."""

    rms: np.ndarray
    onset_env: np.ndarray
    chroma: np.ndarray | None
    mfcc: np.ndarray | None
    n_frames: int


def analyze_audio(data: bytes, filename_hint: str = "") -> TrackAnalysis:
    """Decode `data` as audio and return its duration, tempo, beats, an
    estimated global key, and transition candidates.

    `filename_hint` is only used to preserve a file suffix for the decoder;
    it is never used as a storage path.
    """
    suffix = safe_temp_suffix(filename_hint)

    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)

        # The file handle above is fully closed before librosa opens the
        # path, which avoids sharing-violation errors on Windows.
        y, sr = _decode_mono(tmp_path)
        return _analyze_signal(y, sr)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            # Already gone, or a decoder still had it briefly open; either
            # way there is nothing further we can safely do here.
            pass


def _decode_mono(path: str) -> tuple[np.ndarray, float]:
    try:
        y, sr = librosa.load(path, sr=None, mono=True)
    except Exception as exc:
        raise AudioAnalysisError("Could not decode audio file.") from exc

    if y.size == 0:
        raise AudioAnalysisError("Audio file contains no audio data.")

    return y, sr


def _analyze_signal(y: np.ndarray, sr: float) -> TrackAnalysis:
    duration_seconds = float(librosa.get_duration(y=y, sr=sr))
    tempo_bpm, beats = _detect_tempo_and_beats(y, sr)

    features = _compute_track_features(y, sr)

    estimated_key: str | None = None
    estimated_mode: str | None = None
    key_confidence = 0.0
    if features is not None and features.chroma is not None:
        estimated_key, estimated_mode, key_confidence = _estimate_key(
            features.chroma.mean(axis=1)
        )

    try:
        entry_candidates, exit_candidates = _extract_candidates(
            sr, beats, duration_seconds, features
        )
    except (
        librosa.LibrosaError,
        ValueError,
        IndexError,
        RuntimeError,
        np.linalg.LinAlgError,
    ):
        entry_candidates, exit_candidates = [], []

    return TrackAnalysis(
        duration_seconds=round(duration_seconds, 3),
        tempo_bpm=round(tempo_bpm, 2),
        beat_count=len(beats),
        beats=beats,
        estimated_key=estimated_key,
        estimated_mode=estimated_mode,
        key_confidence=round(key_confidence, 4),
        entry_candidates=entry_candidates,
        exit_candidates=exit_candidates,
    )


def _detect_tempo_and_beats(y: np.ndarray, sr: float) -> tuple[float, list[float]]:
    """Best-effort tempo/beat detection.

    Confident detection is not guaranteed for every input (silence, noise,
    very short clips, ...); any failure here degrades to "no tempo/beats
    detected" rather than propagating an error, since the audio itself
    decoded successfully.
    """
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    except (
        librosa.LibrosaError,
        ValueError,
        IndexError,
        RuntimeError,
        np.linalg.LinAlgError,
    ):
        return 0.0, []

    tempo_bpm = _as_scalar_tempo(tempo)

    if beat_frames.size == 0:
        return tempo_bpm, []

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beats = sorted(float(t) for t in beat_times if np.isfinite(t))
    beats = [round(t, 3) for t in beats]

    return tempo_bpm, beats


def _as_scalar_tempo(tempo: float | np.floating | np.integer | np.ndarray) -> float:
    """Normalize librosa's tempo return value to a plain, finite float.

    Depending on librosa version and inputs, `beat_track` may return tempo
    as a Python float, a NumPy scalar, or a 1-element (or empty) ndarray.
    """
    values = np.atleast_1d(np.asarray(tempo, dtype=float))
    if values.size == 0 or not np.isfinite(values[0]):
        return 0.0
    return float(values[0])


#  Named (rather than inlined) so `except` clauses reference it by name —
#  works around a ruff-format bug (observed with ruff 0.16.7) that can
#  strip the required parentheses from an inline multi-exception tuple in
#  an `except` clause, producing invalid Python 3 syntax.
_FEATURE_EXTRACTION_ERRORS = (librosa.LibrosaError, ValueError, RuntimeError)


def _compute_track_features(y: np.ndarray, sr: float) -> _TrackFeatures | None:
    """Computes every per-frame feature the rest of this module needs,
    exactly once. Chroma/MFCC failure degrades gracefully (structural and
    harmonic features become unavailable) rather than failing analysis
    entirely, since tempo/beats/energy can still be useful on their own."""
    try:
        rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
    except _FEATURE_EXTRACTION_ERRORS:
        return None

    chroma: np.ndarray | None
    mfcc: np.ndarray | None
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP_LENGTH, n_mfcc=13)
    except _FEATURE_EXTRACTION_ERRORS:
        chroma = None
        mfcc = None

    lengths = [len(rms), len(onset_env)]
    if chroma is not None and mfcc is not None:
        lengths += [chroma.shape[1], mfcc.shape[1]]
    n_frames = min(lengths)
    if n_frames == 0:
        return None

    rms = rms[:n_frames]
    onset_env = onset_env[:n_frames]
    if chroma is not None and mfcc is not None:
        chroma = chroma[:, :n_frames]
        mfcc = mfcc[:, :n_frames]

    return _TrackFeatures(
        rms=rms, onset_env=onset_env, chroma=chroma, mfcc=mfcc, n_frames=n_frames
    )


def _estimate_key(chroma_mean: np.ndarray) -> tuple[str | None, str | None, float]:
    """Krumhansl-Schmuckler key estimation from an aggregated 12-bin chroma
    vector. Returns (pitch_class, mode, confidence), or (None, None, 0.0)
    when the signal is too weak/ambiguous to trust — never a guessed key.
    Does not alter audio pitch; this is analysis only.

    Confidence formula: let `best` and `second_best` be the highest and
    second-highest Pearson correlations across all 24 candidates (12
    pitch classes x major/minor).

        base   = clamp01((best + 1) / 2)              in [0, 1]
        margin = max(0, best - second_best)             in [0, 2]
        margin_confidence = clamp01(margin / KEY_MARGIN_SCALE)
        confidence = clamp01(base * (0.5 + 0.5 * margin_confidence))

    `base` alone rewards a strong absolute match; `margin_confidence`
    additionally rewards a *clear* winner over the runner-up, so a track
    that fits two different keys almost equally well (e.g. a key and its
    relative major/minor, or two unrelated keys in a muddled mix) reports
    lower confidence than one with the same top correlation but an
    isolated winner. The 0.5 floor on the margin factor means an
    absolutely strong but perfectly tied match still keeps some
    confidence rather than being zeroed outright by ambiguity alone.
    """
    if float(np.sum(chroma_mean)) < 1e-6:
        return None, None, 0.0

    best_key: str | None = None
    best_mode: str | None = None
    best_correlation = -2.0  # below any possible Pearson correlation
    second_best_correlation = -2.0

    for mode, profile in (
        ("major", KRUMHANSL_MAJOR_PROFILE),
        ("minor", KRUMHANSL_MINOR_PROFILE),
    ):
        for shift in range(12):
            rotated_profile = np.roll(profile, shift)
            correlation = _pearson_correlation(chroma_mean, rotated_profile)
            if correlation > best_correlation:
                second_best_correlation = best_correlation
                best_correlation = correlation
                best_key = PITCH_CLASSES[shift]
                best_mode = mode
            elif correlation > second_best_correlation:
                second_best_correlation = correlation

    base_confidence = _clamp01((best_correlation + 1.0) / 2.0)
    margin = max(0.0, best_correlation - second_best_correlation)
    margin_confidence = _clamp01(margin / KEY_MARGIN_SCALE)
    confidence = _clamp01(base_confidence * (0.5 + 0.5 * margin_confidence))

    if confidence < KEY_CONFIDENCE_MINIMUM:
        return None, None, 0.0

    return best_key, best_mode, confidence


def _pearson_correlation(a: np.ndarray, b: np.ndarray) -> float:
    a_centered = a - a.mean()
    b_centered = b - b.mean()
    denom = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denom <= 1e-9:
        return 0.0
    return float(np.dot(a_centered, b_centered) / denom)


def _clamp01(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _extract_candidates(
    sr: float,
    beats: list[float],
    duration_seconds: float,
    features: _TrackFeatures | None,
) -> tuple[list[TransitionCandidate], list[TransitionCandidate]]:
    """Beat-synchronous transition-candidate scoring.

    For every detected beat: short-term RMS energy just before/after it and
    local onset strength right at it (M6's "boundary strength"), PLUS a
    longer-context structural-change strength (see _structure_and_local_key)
    and that beat's own local key/mode. Candidates are then ranked,
    separately per role, only within a plausible track-position range.

    Returns (entry_candidates, exit_candidates); either can be empty (very
    short track, too few beats, failed feature extraction, or no beat
    within the eligible position range) — callers fall back to a
    deterministic beat choice when that happens rather than treating it as
    an error, exactly as in M6.
    """
    if features is None or len(beats) < 4 or duration_seconds <= 0:
        return [], []

    rms = features.rms
    onset_env = features.onset_env
    n_frames = features.n_frames
    chroma = features.chroma
    mfcc = features.mfcc
    has_harmonic_features = chroma is not None and mfcc is not None

    beat_frames = np.clip(
        librosa.time_to_frames(np.asarray(beats), sr=sr, hop_length=HOP_LENGTH),
        0,
        n_frames - 1,
    )

    n_beats = len(beats)
    energy_before = np.zeros(n_beats)
    energy_after = np.zeros(n_beats)
    boundary_strength = np.zeros(n_beats)
    structure_strength = np.zeros(n_beats)
    local_keys: list[str | None] = [None] * n_beats
    local_modes: list[str | None] = [None] * n_beats
    local_key_confidences = np.zeros(n_beats)
    local_timbres: list[list[float] | None] = [None] * n_beats

    for i in range(n_beats):
        frame = beat_frames[i]

        context_start = max(0, i - CANDIDATE_CONTEXT_BEATS)
        context_end = min(n_beats - 1, i + CANDIDATE_CONTEXT_BEATS)
        start_frame = beat_frames[context_start]
        end_frame = beat_frames[context_end]

        energy_before[i] = (
            float(np.mean(rms[start_frame : frame + 1]))
            if frame > start_frame
            else float(rms[frame])
        )
        energy_after[i] = (
            float(np.mean(rms[frame : end_frame + 1]))
            if end_frame > frame
            else float(rms[frame])
        )

        onset_start = max(0, frame - 2)
        onset_end = min(n_frames, frame + 3)
        boundary_strength[i] = float(np.mean(onset_env[onset_start:onset_end]))

        if not has_harmonic_features:
            continue

        structure_strength[i] = _structure_strength_at(
            chroma, mfcc, beat_frames, i, n_beats
        )
        local_keys[i], local_modes[i], local_key_confidences[i] = _local_key_at(
            chroma, beat_frames, i, n_beats
        )
        local_timbres[i] = _local_timbre_at(mfcc, beat_frames, i, n_beats)

    energy_change = np.abs(energy_after - energy_before)
    positions = np.asarray(beats) / duration_seconds

    exit_candidates = _rank_candidates(
        beats,
        positions,
        energy_change,
        boundary_strength,
        structure_strength,
        energy_before,
        energy_after,
        local_keys,
        local_modes,
        local_key_confidences,
        local_timbres,
        position_range=SONG_A_EXIT_POSITION_RANGE,
        preferred_position=SONG_A_EXIT_PREFERRED_POSITION,
    )
    entry_candidates = _rank_candidates(
        beats,
        positions,
        energy_change,
        boundary_strength,
        structure_strength,
        energy_before,
        energy_after,
        local_keys,
        local_modes,
        local_key_confidences,
        local_timbres,
        position_range=SONG_B_ENTRY_POSITION_RANGE,
        preferred_position=SONG_B_ENTRY_PREFERRED_POSITION,
    )

    return entry_candidates, exit_candidates


def _structure_strength_at(
    chroma: np.ndarray,
    mfcc: np.ndarray,
    beat_frames: np.ndarray,
    i: int,
    n_beats: int,
) -> float:
    """Compares musical context (harmony via chroma, timbre via MFCC) in
    the STRUCTURE_CONTEXT_BEATS window before beat `i` against the window
    after it, as a cosine distance in each feature space. The two
    distances are averaged, which keeps the result in [0, 1] by
    construction (each cosine distance already is) without needing a
    separate batch-relative normalization step at this point."""
    before_beat = max(0, i - STRUCTURE_CONTEXT_BEATS)
    after_beat = min(n_beats - 1, i + STRUCTURE_CONTEXT_BEATS)
    frame = beat_frames[i]
    before_frame = beat_frames[before_beat]
    after_frame = beat_frames[after_beat]

    chroma_before = _mean_column(chroma, before_frame, frame)
    chroma_after = _mean_column(chroma, frame, after_frame)
    mfcc_before = _mean_column(mfcc, before_frame, frame)
    mfcc_after = _mean_column(mfcc, frame, after_frame)

    chroma_distance = _cosine_distance(chroma_before, chroma_after)
    mfcc_distance = _cosine_distance(mfcc_before, mfcc_after)
    return 0.5 * chroma_distance + 0.5 * mfcc_distance


def _local_key_at(
    chroma: np.ndarray,
    beat_frames: np.ndarray,
    i: int,
    n_beats: int,
) -> tuple[str | None, str | None, float]:
    """Estimated key/mode from a LOCAL_KEY_CONTEXT_BEATS window around beat
    `i` — a compact (key, mode, confidence) summary rather than returning
    any chroma data itself, since the frontend never needs a full
    chromagram and this stays trivially small/serializable."""
    local_chroma_mean = _local_context_mean(chroma, beat_frames, i, n_beats)
    return _estimate_key(local_chroma_mean)


def _local_timbre_at(
    mfcc: np.ndarray,
    beat_frames: np.ndarray,
    i: int,
    n_beats: int,
) -> list[float]:
    """A compact local MFCC summary (mean of the 13 coefficients) over the
    same LOCAL_KEY_CONTEXT_BEATS window as _local_key_at, used for M12's
    cross-track timbral/spectral compatibility term (see
    services/transition_planner.py). MFCC describes broad spectral/timbral
    character (roughly: instrumentation and tonal texture) — a distinct
    signal from chroma's pitch-class content, so this is never derived
    from local_key_at's result."""
    local_mfcc_mean = _local_context_mean(mfcc, beat_frames, i, n_beats)
    return [round(float(value), 4) for value in local_mfcc_mean]


def _local_context_mean(
    matrix: np.ndarray,
    beat_frames: np.ndarray,
    i: int,
    n_beats: int,
) -> np.ndarray:
    before_beat = max(0, i - LOCAL_KEY_CONTEXT_BEATS)
    after_beat = min(n_beats - 1, i + LOCAL_KEY_CONTEXT_BEATS)
    start_frame = beat_frames[before_beat]
    end_frame = max(beat_frames[after_beat], start_frame + 1)
    return _mean_column(matrix, start_frame, end_frame)


def _mean_column(matrix: np.ndarray, start_frame: int, end_frame: int) -> np.ndarray:
    if end_frame > start_frame:
        return matrix[:, start_frame:end_frame].mean(axis=1)
    return matrix[:, start_frame]


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """0.0 = same direction (no detectable change), 1.0 = maximally
    dissimilar. Bounded in [0, 1] by construction via (1 - cosine) / 2."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a <= 1e-9 or norm_b <= 1e-9:
        return 0.0
    cosine_similarity = float(np.dot(a, b) / (norm_a * norm_b))
    cosine_similarity = min(max(cosine_similarity, -1.0), 1.0)  # guard fp drift
    return (1.0 - cosine_similarity) / 2.0


def _rank_candidates(
    beats: list[float],
    positions: np.ndarray,
    energy_change: np.ndarray,
    boundary_strength: np.ndarray,
    structure_strength: np.ndarray,
    energy_before: np.ndarray,
    energy_after: np.ndarray,
    local_keys: list[str | None],
    local_modes: list[str | None],
    local_key_confidences: np.ndarray,
    local_timbres: list[list[float] | None],
    *,
    position_range: tuple[float, float],
    preferred_position: float,
) -> list[TransitionCandidate]:
    low, high = position_range
    eligible = np.where((positions >= low) & (positions <= high))[0]
    if eligible.size == 0:
        return []

    norm_structure = _normalize(structure_strength[eligible])
    norm_boundary = _normalize(boundary_strength[eligible])
    norm_energy = _normalize(energy_change[eligible])
    position_distance = np.abs(positions[eligible] - preferred_position)
    norm_position = 1.0 - _normalize(position_distance)

    scores = (
        WEIGHT_STRUCTURE * norm_structure
        + WEIGHT_BOUNDARY_STRENGTH * norm_boundary
        + WEIGHT_ENERGY_CHANGE * norm_energy
        + WEIGHT_POSITION * norm_position
    )

    ranked_order = np.argsort(-scores)[:MAX_CANDIDATES_PER_ROLE]

    candidates = []
    for rank_pos in ranked_order:
        i = int(eligible[rank_pos])
        candidates.append(
            TransitionCandidate(
                beat_index=i,
                time_seconds=beats[i],
                score=round(float(scores[rank_pos]), 4),
                boundary_strength=round(float(boundary_strength[i]), 6),
                energy_before=round(float(energy_before[i]), 6),
                energy_after=round(float(energy_after[i]), 6),
                structure_strength=round(float(structure_strength[i]), 4),
                local_key=local_keys[i],
                local_mode=local_modes[i],
                local_key_confidence=round(float(local_key_confidences[i]), 4),
                local_timbre=local_timbres[i],
            )
        )
    return candidates


def _normalize(values: np.ndarray) -> np.ndarray:
    """Min-max scale to [0, 1]; an all-equal input maps to all zeros
    (rather than dividing by zero) since there's no useful signal to rank."""
    span = float(values.max() - values.min())
    if span <= 1e-9 or not math.isfinite(span):
        return np.zeros_like(values)
    return (values - values.min()) / span
