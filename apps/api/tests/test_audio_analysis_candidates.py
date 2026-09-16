import numpy as np

from app.services.audio_analysis import (
    MAX_CANDIDATES_PER_ROLE,
    SONG_A_EXIT_POSITION_RANGE,
    SONG_B_ENTRY_POSITION_RANGE,
    _extract_candidates,
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


def test_candidates_reference_valid_beat_indices() -> None:
    y, beats = _make_track_with_energy_step(120.0, 40.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert 0 <= candidate.beat_index < len(beats)


def test_candidate_timestamps_match_the_original_beats_array_exactly() -> None:
    y, beats = _make_track_with_energy_step(120.0, 40.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert candidate.time_seconds == beats[candidate.beat_index]


def test_candidate_counts_are_bounded() -> None:
    y, beats = _make_track_with_energy_step(120.0, 90.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    assert len(entry_candidates) <= MAX_CANDIDATES_PER_ROLE
    assert len(exit_candidates) <= MAX_CANDIDATES_PER_ROLE


def test_very_few_beats_returns_no_candidates_rather_than_crashing() -> None:
    y, beats = _make_track_with_energy_step(120.0, 2.0)
    beats = beats[:2]  # fewer than the minimum needed for context windows
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    assert entry_candidates == []
    assert exit_candidates == []


def test_exit_candidates_are_confined_to_the_eligible_position_range() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    _entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    low, high = SONG_A_EXIT_POSITION_RANGE
    for candidate in exit_candidates:
        position = candidate.time_seconds / duration
        assert low <= position <= high


def test_entry_candidates_are_confined_to_the_eligible_position_range() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.2)
    duration = len(y) / 22050

    entry_candidates, _exit_candidates = _extract_candidates(y, 22050, beats, duration)

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

    _entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    assert exit_candidates, "expected at least one eligible exit candidate"
    top = exit_candidates[0]
    assert abs(top.time_seconds / duration - 0.7) < 0.1


def test_entry_candidates_rank_the_eligible_energy_change_highest() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.2)
    duration = len(y) / 22050

    entry_candidates, _exit_candidates = _extract_candidates(y, 22050, beats, duration)

    assert entry_candidates, "expected at least one eligible entry candidate"
    top = entry_candidates[0]
    assert abs(top.time_seconds / duration - 0.2) < 0.1


def test_candidates_are_sorted_by_descending_score() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    _entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    scores = [c.score for c in exit_candidates]
    assert scores == sorted(scores, reverse=True)


def test_energy_and_boundary_fields_are_non_negative_and_finite() -> None:
    y, beats = _make_track_with_energy_step(120.0, 60.0, step_fraction=0.7)
    duration = len(y) / 22050

    entry_candidates, exit_candidates = _extract_candidates(y, 22050, beats, duration)

    for candidate in [*entry_candidates, *exit_candidates]:
        assert candidate.energy_before >= 0
        assert candidate.energy_after >= 0
        assert candidate.boundary_strength >= 0
        assert np.isfinite(candidate.score)
