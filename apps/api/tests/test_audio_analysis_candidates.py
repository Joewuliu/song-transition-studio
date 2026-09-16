import librosa
import numpy as np

from app.services.audio_analysis import (
    HOP_LENGTH,
    MAX_CANDIDATES_PER_ROLE,
    SONG_A_EXIT_POSITION_RANGE,
    SONG_B_ENTRY_POSITION_RANGE,
    _compute_track_features,
    _extract_candidates,
    _structure_strength_at,
)


def _make_track_with_energy_step(
    bpm: float,
    duration: float,
    sr: int = 22050,
    step_fraction: float = 0.7,
    quiet_amplitude: float = 0.15,
    loud_amplitude: float = 0.8,
) -> tuple[np.ndarray, list[float]]:
    """A click track that's quiet up to `step_fraction` of its duration and
    loud afterward — gives candidate scoring a clear, deterministic energy
    change to find."""
    interval = 60.0 / bpm
    n_samples = int(sr * duration)
    y = np.zeros(n_samples, dtype=np.float32)
    click_len = int(sr * 0.03)

    beats: list[float] = []
    t = 0.0
    while t < duration:
        amplitude = (
            loud_amplitude if (t / duration) > step_fraction else quiet_amplitude
        )
        start = int(t * sr)
        end = min(start + click_len, n_samples)
        click = (
            amplitude
            * np.sin(2 * np.pi * 400 * np.arange(end - start) / sr)
            * np.hanning(end - start)
        ).astype(np.float32)
        y[start:end] += click
        beats.append(round(t, 6))
        t += interval

    return y, beats


def _make_track_with_harmonic_shift(
    bpm: float,
    duration: float,
    sr: int = 22050,
    shift_fraction: float = 0.5,
    freq_before: float = 220.0,  # A
    freq_after: float = 293.66,  # D — a different pitch class, not just an
    # octave of the same one (chroma folds octaves together, so a same-
    # pitch-class octave jump wouldn't show up as a chroma change).
) -> tuple[np.ndarray, list[float]]:
    """A continuous tone that changes pitch class partway through — gives
    structural scoring a clear, deterministic harmonic/timbral shift to
    find, independent of any onset/energy change (amplitude stays constant
    throughout)."""
    n_samples = int(sr * duration)
    t = np.arange(n_samples) / sr
    shift_sample = int(shift_fraction * n_samples)

    y = np.zeros(n_samples, dtype=np.float32)
    y[:shift_sample] = 0.3 * np.sin(2 * np.pi * freq_before * t[:shift_sample])
    y[shift_sample:] = 0.3 * np.sin(2 * np.pi * freq_after * t[shift_sample:])

    interval = 60.0 / bpm
    beats: list[float] = []
    t_beat = 0.0
    while t_beat < duration:
        beats.append(round(t_beat, 6))
        t_beat += interval

    return y.astype(np.float32), beats


def _extract(y: np.ndarray, sr: int, beats: list[float], duration: float):
    features = _compute_track_features(y, sr)
    return _extract_candidates(sr, beats, duration, features)


def test_candidates_reference_valid_beat_indices() -> None:
    y, beats = _make_track_with_energy_step(120.0, 40.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert 0 <= candidate.beat_index < len(beats)


def test_candidate_timestamps_match_the_original_beats_array_exactly() -> None:
    y, beats = _make_track_with_energy_step(120.0, 40.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert candidate.time_seconds == beats[candidate.beat_index]


def test_candidate_counts_are_bounded() -> None:
    y, beats = _make_track_with_energy_step(120.0, 90.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    assert len(entry_candidates) <= MAX_CANDIDATES_PER_ROLE
    assert len(exit_candidates) <= MAX_CANDIDATES_PER_ROLE


def test_very_few_beats_returns_no_candidates_rather_than_crashing() -> None:
    y, beats = _make_track_with_energy_step(120.0, 2.0)
    beats = beats[:2]  # fewer than the minimum needed for context windows
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    assert entry_candidates == []
    assert exit_candidates == []


def test_exit_candidates_are_confined_to_the_eligible_position_range() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    _entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    low, high = SONG_A_EXIT_POSITION_RANGE
    for candidate in exit_candidates:
        position = candidate.time_seconds / duration
        assert low <= position <= high


def test_entry_candidates_are_confined_to_the_eligible_position_range() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.2)
    duration = len(y) / 22050

    entry_candidates, _exit_candidates = _extract(y, 22050, beats, duration)

    low, high = SONG_B_ENTRY_POSITION_RANGE
    for candidate in entry_candidates:
        position = candidate.time_seconds / duration
        assert low <= position <= high


def test_exit_candidates_rank_the_eligible_energy_change_highest() -> None:
    """The synthetic energy step sits at 70% of the track — inside Song A's
    eligible exit range — so the top-ranked exit candidate should land
    close to it, not merely be "some later beat"."""
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    _entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    assert exit_candidates, "expected at least one eligible exit candidate"
    top = exit_candidates[0]
    assert abs(top.time_seconds / duration - 0.7) < 0.1


def test_entry_candidates_rank_the_eligible_energy_change_highest() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.2)
    duration = len(y) / 22050

    entry_candidates, _exit_candidates = _extract(y, 22050, beats, duration)

    assert entry_candidates, "expected at least one eligible entry candidate"
    top = entry_candidates[0]
    assert abs(top.time_seconds / duration - 0.2) < 0.1


def test_candidates_are_sorted_by_descending_score() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    _entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    scores = [c.score for c in exit_candidates]
    assert scores == sorted(scores, reverse=True)


def test_energy_and_boundary_fields_are_non_negative_and_finite() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert candidate.energy_before >= 0
        assert candidate.energy_after >= 0
        assert candidate.boundary_strength >= 0
        assert np.isfinite(candidate.score)


# ---------------------------------------------------------------------------
# M7: structural-change strength
# ---------------------------------------------------------------------------


def test_structure_strength_values_are_finite_and_normalized() -> None:
    y, beats = _make_track_with_harmonic_shift(120.0, 60.0, shift_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert np.isfinite(candidate.structure_strength)
        assert 0.0 <= candidate.structure_strength <= 1.0


def test_structural_change_is_stronger_near_a_shift_than_in_a_stable_region() -> None:
    y, beats = _make_track_with_harmonic_shift(120.0, 40.0, shift_fraction=0.5)
    sr = 22050

    features = _compute_track_features(y, sr)
    assert features is not None
    assert features.chroma is not None and features.mfcc is not None

    beat_frames = np.clip(
        librosa.time_to_frames(np.asarray(beats), sr=sr, hop_length=HOP_LENGTH),
        0,
        features.n_frames - 1,
    )
    n_beats = len(beats)

    # One beat right at the harmonic shift (20s into a 40s clip), one beat
    # from an early, harmonically stable region far from it.
    shift_beat_index = min(range(n_beats), key=lambda i: abs(beats[i] - 20.0))
    stable_beat_index = min(range(n_beats), key=lambda i: abs(beats[i] - 5.0))

    strength_at_shift = _structure_strength_at(
        features.chroma, features.mfcc, beat_frames, shift_beat_index, n_beats
    )
    strength_stable = _structure_strength_at(
        features.chroma, features.mfcc, beat_frames, stable_beat_index, n_beats
    )

    assert strength_at_shift > strength_stable
