import numpy as np

from app.services.audio_analysis import (
    KEY_CONFIDENCE_MINIMUM,
    _compute_track_features,
    _estimate_key,
)

SR = 22050

# Approximate note frequencies (Hz), one octave, used to build simple
# synthetic chords for deterministic key-estimation tests.
NOTE_FREQUENCIES = {
    "C": 261.63,
    "C#": 277.18,
    "D": 293.66,
    "D#": 311.13,
    "E": 329.63,
    "F": 349.23,
    "F#": 369.99,
    "G": 392.00,
    "G#": 415.30,
    "A": 440.00,
    "A#": 466.16,
    "B": 493.88,
}
_NOTE_ORDER = list(NOTE_FREQUENCIES.keys())


def _triad_frequencies(root: str, minor: bool) -> list[float]:
    root_index = _NOTE_ORDER.index(root)
    third_semitones = 3 if minor else 4
    third = _NOTE_ORDER[(root_index + third_semitones) % 12]
    fifth = _NOTE_ORDER[(root_index + 7) % 12]
    return [NOTE_FREQUENCIES[root], NOTE_FREQUENCIES[third], NOTE_FREQUENCIES[fifth]]


def _make_chord_tone(
    freqs: list[float], duration: float = 20.0, sr: int = SR, amplitude: float = 0.2
) -> np.ndarray:
    t = np.arange(int(sr * duration)) / sr
    y = np.zeros_like(t)
    for freq in freqs:
        y += amplitude * np.sin(2 * np.pi * freq * t)
    return y.astype(np.float32)


def _chroma_mean_for(y: np.ndarray) -> np.ndarray:
    features = _compute_track_features(y, SR)
    assert features is not None
    assert features.chroma is not None
    return features.chroma.mean(axis=1)


def test_recognizes_synthetic_major_harmony() -> None:
    y = _make_chord_tone(_triad_frequencies("C", minor=False))
    key, mode, confidence = _estimate_key(_chroma_mean_for(y))

    assert key == "C"
    assert mode == "major"
    assert confidence >= KEY_CONFIDENCE_MINIMUM


def test_recognizes_synthetic_major_harmony_at_a_different_root() -> None:
    y = _make_chord_tone(_triad_frequencies("G", minor=False))
    key, mode, confidence = _estimate_key(_chroma_mean_for(y))

    assert key == "G"
    assert mode == "major"
    assert confidence >= KEY_CONFIDENCE_MINIMUM


def test_recognizes_synthetic_minor_harmony() -> None:
    y = _make_chord_tone(_triad_frequencies("A", minor=True))
    key, mode, confidence = _estimate_key(_chroma_mean_for(y))

    assert key == "A"
    assert mode == "minor"
    assert confidence >= KEY_CONFIDENCE_MINIMUM


def test_recognizes_synthetic_minor_harmony_at_a_different_root() -> None:
    y = _make_chord_tone(_triad_frequencies("E", minor=True))
    key, mode, confidence = _estimate_key(_chroma_mean_for(y))

    assert key == "E"
    assert mode == "minor"
    assert confidence >= KEY_CONFIDENCE_MINIMUM


def test_silence_does_not_produce_a_confident_fake_key() -> None:
    key, mode, confidence = _estimate_key(np.zeros(12))

    assert key is None
    assert mode is None
    assert confidence == 0.0


def test_near_silent_audio_does_not_produce_a_confident_fake_key() -> None:
    y = np.zeros(int(SR * 5.0), dtype=np.float32)
    key, mode, confidence = _estimate_key(_chroma_mean_for(y))

    assert key is None
    assert mode is None
    assert confidence == 0.0


def test_partial_key_ambiguity_lowers_confidence_without_changing_the_key() -> None:
    """Mixing in a quiet, harmonically distant (tritone-related) second
    chord makes the correlation margin between the winning key and the
    runner-up smaller, without changing which key wins outright. Confidence
    should drop relative to the clean single-chord case, even though the
    detected key/mode are unchanged."""
    clear_y = _make_chord_tone(_triad_frequencies("C", minor=False))
    ambiguous_y = clear_y + _make_chord_tone(
        _triad_frequencies("F#", minor=False), amplitude=0.08
    )

    clear_key, clear_mode, clear_confidence = _estimate_key(_chroma_mean_for(clear_y))
    ambiguous_key, ambiguous_mode, ambiguous_confidence = _estimate_key(
        _chroma_mean_for(ambiguous_y)
    )

    assert clear_key == ambiguous_key == "C"
    assert clear_mode == ambiguous_mode == "major"
    assert ambiguous_confidence < clear_confidence
    assert ambiguous_confidence >= KEY_CONFIDENCE_MINIMUM


def test_strong_key_ambiguity_does_not_produce_a_confident_key() -> None:
    """Equal-amplitude, harmonically distant (tritone-related) chords give
    the two best-matching keys nearly identical correlation — a genuinely
    ambiguous signal that must not be reported as confident, even though
    each chord alone would be recognized easily."""
    y = _make_chord_tone(
        _triad_frequencies("C", minor=False), amplitude=0.15
    ) + _make_chord_tone(_triad_frequencies("F#", minor=False), amplitude=0.15)

    key, mode, confidence = _estimate_key(_chroma_mean_for(y))

    assert key is None
    assert mode is None
    assert confidence < KEY_CONFIDENCE_MINIMUM


def test_flat_ambiguous_chroma_does_not_produce_a_confident_key() -> None:
    """A chroma vector with equal energy across all 12 pitch classes has no
    tonal center at all — this must not be reported as a confident key."""
    key, mode, confidence = _estimate_key(np.ones(12))

    assert key is None
    assert mode is None
    assert confidence < KEY_CONFIDENCE_MINIMUM


def test_confidence_is_always_finite_and_in_documented_range() -> None:
    for chroma in (
        np.zeros(12),
        np.ones(12),
        _chroma_mean_for(_make_chord_tone(_triad_frequencies("D", minor=False))),
        _chroma_mean_for(_make_chord_tone(_triad_frequencies("F#", minor=True))),
    ):
        _key, _mode, confidence = _estimate_key(chroma)
        assert np.isfinite(confidence)
        assert 0.0 <= confidence <= 1.0


def test_does_not_alter_audio_pitch() -> None:
    """Key estimation is read-only analysis: the input signal must be
    unchanged by the call (no in-place mutation, no pitch-shifting)."""
    y = _make_chord_tone(_triad_frequencies("C", minor=False))
    y_before = y.copy()

    _estimate_key(_chroma_mean_for(y))

    assert np.array_equal(y, y_before)
