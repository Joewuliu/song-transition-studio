"""Musical analysis (tempo/beats) for uploaded audio, backed by librosa.

Uploaded audio is never kept: each call writes the given bytes to a private
temporary file (librosa/soundfile need a real path for some codecs), decodes
it, and removes the file again before returning.
"""

import math
import os
import tempfile
from pathlib import Path

import librosa
import numpy as np

from app.schemas import TrackAnalysis, TransitionCandidate

# Beats of context averaged on each side of a candidate beat when scoring
# it — smoothing/context only, *not* a bar or measure (no 4/4 assumption).
CANDIDATE_CONTEXT_BEATS = 2

# Cap on how many ranked candidates are returned per role — small shortlists,
# not the full per-frame feature data.
MAX_CANDIDATES_PER_ROLE = 10

# Track-position eligibility windows (fraction of duration) for each role.
# Position is only ONE scoring input (see _rank_candidates); these ranges
# just exclude positions that could never be a sensible transition point
# (e.g. right at the very start/end, where too little audio would remain).
SONG_A_EXIT_POSITION_RANGE = (0.55, 0.92)
SONG_B_ENTRY_POSITION_RANGE = (0.03, 0.45)

# Where each range's score peaks — matches the deterministic fallback
# positions one-for-one, so "no strong candidate found" and "candidate
# found but position-neutral" land in the same neighborhood.
SONG_A_EXIT_PREFERRED_POSITION = 0.75
SONG_B_ENTRY_PREFERRED_POSITION = 0.15

# Relative weights for ranking within a role's eligible candidates. Musical
# change (boundary strength, energy change) is weighted above raw position.
WEIGHT_BOUNDARY_STRENGTH = 0.5
WEIGHT_ENERGY_CHANGE = 0.3
WEIGHT_POSITION = 0.2


class AudioAnalysisError(Exception):
    """Raised when uploaded audio cannot be decoded or analyzed."""


def analyze_audio(data: bytes, filename_hint: str = "") -> TrackAnalysis:
    """Decode `data` as audio and return its duration, tempo, and beats.

    `filename_hint` is only used to preserve a file suffix for the decoder;
    it is never used as a storage path.
    """
    suffix = Path(filename_hint).suffix

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

    try:
        entry_candidates, exit_candidates = _extract_candidates(
            y, sr, beats, duration_seconds
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


def _extract_candidates(
    y: np.ndarray, sr: float, beats: list[float], duration_seconds: float
) -> tuple[list[TransitionCandidate], list[TransitionCandidate]]:
    """Beat-synchronous transition-candidate scoring.

    For every detected beat, measures local RMS energy just before and
    after it (over a small window of neighboring beats — context/smoothing
    only, not a bar) and local onset strength right at it ("boundary
    strength": how much the audio is musically changing at that instant).
    Candidates are then ranked, separately per role, only within a
    plausible track-position range for that role.

    Returns (entry_candidates, exit_candidates); either can be empty
    (very short track, too few beats, or no beat within the eligible
    position range) — callers fall back to a deterministic beat choice
    when that happens rather than treating it as an error.
    """
    if len(beats) < 4 or duration_seconds <= 0:
        return [], []

    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

    n_frames = min(len(rms), len(onset_env))
    if n_frames == 0:
        return [], []
    rms = rms[:n_frames]
    onset_env = onset_env[:n_frames]

    beat_frames = np.clip(
        librosa.time_to_frames(np.asarray(beats), sr=sr, hop_length=hop_length),
        0,
        n_frames - 1,
    )

    n_beats = len(beats)
    energy_before = np.zeros(n_beats)
    energy_after = np.zeros(n_beats)
    boundary_strength = np.zeros(n_beats)

    for i in range(n_beats):
        context_start = max(0, i - CANDIDATE_CONTEXT_BEATS)
        context_end = min(n_beats - 1, i + CANDIDATE_CONTEXT_BEATS)
        frame = beat_frames[i]
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

    energy_change = np.abs(energy_after - energy_before)
    positions = np.asarray(beats) / duration_seconds

    exit_candidates = _rank_candidates(
        beats,
        positions,
        energy_change,
        boundary_strength,
        energy_before,
        energy_after,
        position_range=SONG_A_EXIT_POSITION_RANGE,
        preferred_position=SONG_A_EXIT_PREFERRED_POSITION,
    )
    entry_candidates = _rank_candidates(
        beats,
        positions,
        energy_change,
        boundary_strength,
        energy_before,
        energy_after,
        position_range=SONG_B_ENTRY_POSITION_RANGE,
        preferred_position=SONG_B_ENTRY_PREFERRED_POSITION,
    )

    return entry_candidates, exit_candidates


def _rank_candidates(
    beats: list[float],
    positions: np.ndarray,
    energy_change: np.ndarray,
    boundary_strength: np.ndarray,
    energy_before: np.ndarray,
    energy_after: np.ndarray,
    *,
    position_range: tuple[float, float],
    preferred_position: float,
) -> list[TransitionCandidate]:
    low, high = position_range
    eligible = np.where((positions >= low) & (positions <= high))[0]
    if eligible.size == 0:
        return []

    norm_boundary = _normalize(boundary_strength[eligible])
    norm_energy = _normalize(energy_change[eligible])
    position_distance = np.abs(positions[eligible] - preferred_position)
    norm_position = 1.0 - _normalize(position_distance)

    scores = (
        WEIGHT_BOUNDARY_STRENGTH * norm_boundary
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
