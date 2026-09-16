import io
import json
import math

import librosa
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app
from app.services.transition_renderer import (
    TransitionRenderError,
    _bass_swap_gains,
    _split_frequency_bands,
    render_transition,
)

client = TestClient(app)


def _make_click_track(
    bpm: float, duration: float, sr: int = 22050, channels: int = 2
) -> tuple[np.ndarray, int]:
    """A synthetic percussive click track at an exact, known BPM."""
    interval = 60.0 / bpm
    n_samples = int(sr * duration)
    y = np.zeros((n_samples, channels), dtype=np.float32)

    click_len = int(sr * 0.01)
    click = (
        np.sin(2 * np.pi * 1000 * np.arange(click_len) / sr) * np.hanning(click_len)
    ).astype(np.float32)

    t = 0.0
    while t < duration:
        start = int(t * sr)
        end = min(start + click_len, n_samples)
        for channel in range(channels):
            y[start:end, channel] += click[: end - start]
        t += interval

    return y, sr


def _wav_bytes(y: np.ndarray, sr: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, y, sr, format="WAV", subtype="FLOAT")
    return buffer.getvalue()


def _write_temp(tmp_path, name: str, data: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _beat_time(bpm: float, beat_index: int) -> float:
    return beat_index * (60.0 / bpm)


def _make_tone(
    duration: float,
    sr: int = 22050,
    channels: int = 2,
    freq: float = 220.0,
    amplitude: float = 0.3,
) -> tuple[np.ndarray, int]:
    """A continuous sine tone (not sparse clicks) — useful for measuring
    relative amplitude/gain rather than beat timing. `amplitude` is kept
    well under 1.0 so gain-trim tests aren't confounded by the renderer's
    anti-clipping safety scale kicking in."""
    n_samples = int(sr * duration)
    t = np.arange(n_samples) / sr
    tone = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    y = np.tile(tone[:, None], (1, channels))
    return y, sr


def _rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


# ---------------------------------------------------------------------------
# Direct service-level tests (no HTTP layer) — these are the fast, precise
# checks for the actual DSP: alignment math, stretch direction, boundaries.
# ---------------------------------------------------------------------------


def test_valid_synthetic_tracks_produce_a_decodable_wav(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 128.0, 120.0
    y_a, sr_a = _make_click_track(song_a_bpm, 20.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 20.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 20),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 20),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    assert sr_out == result.sample_rate
    assert data.shape[0] > 0


def test_output_duration_matches_16_beats_at_song_a_bpm(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 100.0, 95.0
    y_a, sr_a = _make_click_track(song_a_bpm, 15.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 15.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 10),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 10),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    expected_duration = 16 * (60.0 / song_a_bpm)
    assert abs(result.duration_seconds - expected_duration) < 0.05
    assert result.target_bpm == song_a_bpm


def test_output_duration_matches_8_beats(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 120.0, 110.0
    y_a, sr_a = _make_click_track(song_a_bpm, 15.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 15.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 10),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 10),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
        transition_beats=8,
    )

    expected_duration = 8 * (60.0 / song_a_bpm)
    assert abs(result.duration_seconds - expected_duration) < 0.05


def test_output_duration_matches_32_beats(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 120.0, 110.0
    y_a, sr_a = _make_click_track(song_a_bpm, 25.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 25.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 15),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 15),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
        transition_beats=32,
    )

    expected_duration = 32 * (60.0 / song_a_bpm)
    assert abs(result.duration_seconds - expected_duration) < 0.05


def test_output_samples_are_finite_and_within_safe_amplitude(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 128.0, 128.0
    # Loud, fully-overlapping content on both channels to stress the mixer.
    y_a, sr_a = _make_click_track(song_a_bpm, 12.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 12.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 12),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 12),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    assert np.all(np.isfinite(data))
    assert np.max(np.abs(data)) <= 1.0 + 1e-6


def test_stereo_input_produces_stereo_output(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 120.0, 120.0
    y_a, sr_a = _make_click_track(song_a_bpm, 10.0, channels=2)
    y_b, sr_b = _make_click_track(song_b_bpm, 10.0, channels=2)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 8),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 8),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    assert data.shape[1] == 2


def test_different_source_sample_rates_are_handled(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 128.0, 128.0
    y_a, sr_a = _make_click_track(song_a_bpm, 10.0, sr=44100)
    y_b, sr_b = _make_click_track(song_b_bpm, 10.0, sr=16000)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(song_a_bpm, 8),
        song_b_anchor_seconds=_beat_time(song_b_bpm, 8),
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    assert sr_out == result.sample_rate
    assert np.all(np.isfinite(data))


def _render_tone_transition(
    tmp_path,
    *,
    song_a_gain_db: float = 0.0,
    song_b_gain_db: float = 0.0,
    crossfade_bias: float = 0.0,
    song_a_amplitude: float = 0.3,
    song_b_amplitude: float = 0.3,
) -> np.ndarray:
    """Renders a transition between two continuous same-frequency tones
    (same BPM, so no time-stretching is involved) and returns the decoded
    stereo samples — used to measure how gain/bias actually affect the
    mixed output's amplitude, independent of beat-alignment concerns."""
    bpm = 120.0
    y_a, sr_a = _make_tone(10.0, amplitude=song_a_amplitude)
    y_b, sr_b = _make_tone(10.0, amplitude=song_b_amplitude)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=5.0,
        song_b_anchor_seconds=5.0,
        song_a_bpm=bpm,
        song_b_bpm=bpm,
        song_a_gain_db=song_a_gain_db,
        song_b_gain_db=song_b_gain_db,
        crossfade_bias=crossfade_bias,
    )
    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    return data


def test_positive_song_a_gain_increases_its_contribution(tmp_path) -> None:
    # Near the very start of the window, gain_a ~= 1 and gain_b ~= 0 (at
    # bias=0), so this measures Song A's contribution in isolation.
    baseline = _render_tone_transition(tmp_path, song_a_gain_db=0.0)
    boosted = _render_tone_transition(tmp_path, song_a_gain_db=6.0)

    early = slice(0, 50)
    assert _rms(boosted[early]) > _rms(baseline[early]) * 1.3


def test_negative_song_a_gain_decreases_its_contribution(tmp_path) -> None:
    baseline = _render_tone_transition(tmp_path, song_a_gain_db=0.0)
    attenuated = _render_tone_transition(tmp_path, song_a_gain_db=-12.0)

    early = slice(0, 50)
    assert _rms(attenuated[early]) < _rms(baseline[early]) * 0.5


def test_positive_song_b_gain_increases_its_contribution(tmp_path) -> None:
    # Near the very end of the window, gain_b ~= 1 and gain_a ~= 0.
    baseline = _render_tone_transition(tmp_path, song_b_gain_db=0.0)
    boosted = _render_tone_transition(tmp_path, song_b_gain_db=6.0)

    late = slice(-50, None)
    assert _rms(boosted[late]) > _rms(baseline[late]) * 1.3


def test_negative_song_b_gain_decreases_its_contribution(tmp_path) -> None:
    baseline = _render_tone_transition(tmp_path, song_b_gain_db=0.0)
    attenuated = _render_tone_transition(tmp_path, song_b_gain_db=-12.0)

    late = slice(-50, None)
    assert _rms(attenuated[late]) < _rms(baseline[late]) * 0.5


def test_negative_bias_makes_song_b_dominant_earlier(tmp_path) -> None:
    # Song A silent isolates Song B's own gain curve in the mixed output.
    zero_bias = _render_tone_transition(
        tmp_path, crossfade_bias=0.0, song_a_amplitude=0.0
    )
    negative_bias = _render_tone_transition(
        tmp_path, crossfade_bias=-1.0, song_a_amplitude=0.0
    )

    n = zero_bias.shape[0]
    early = slice(int(0.25 * n) - 100, int(0.25 * n) + 100)
    assert _rms(negative_bias[early]) > _rms(zero_bias[early])


def test_positive_bias_makes_song_b_dominant_later(tmp_path) -> None:
    zero_bias = _render_tone_transition(
        tmp_path, crossfade_bias=0.0, song_a_amplitude=0.0
    )
    positive_bias = _render_tone_transition(
        tmp_path, crossfade_bias=1.0, song_a_amplitude=0.0
    )

    n = zero_bias.shape[0]
    early = slice(int(0.25 * n) - 100, int(0.25 * n) + 100)
    assert _rms(positive_bias[early]) < _rms(zero_bias[early])


def test_fade_endpoints_correct_for_extreme_bias_values(tmp_path) -> None:
    # RMS of a sine of amplitude A, averaged over whole cycles, is A/sqrt(2).
    # A 220 Hz tone at 22050 Hz has ~100 samples/cycle, so a 1000-sample
    # window (~10 cycles) is both a robust RMS estimate and still a tiny
    # sliver of the multi-second transition window (gain ~= 1 there).
    tone_amplitude = 0.3
    expected_full_gain_rms = tone_amplitude / math.sqrt(2)
    window = 1000

    for bias in (-1.0, 0.0, 1.0):
        # Song B silent: output should be ~full Song A right at the start,
        # regardless of bias (bias must never move the fade's endpoints).
        song_a_only = _render_tone_transition(
            tmp_path, crossfade_bias=bias, song_b_amplitude=0.0
        )
        start_rms = _rms(song_a_only[:window])
        assert start_rms > 0.9 * expected_full_gain_rms

        # Song A silent: output should be ~full Song B right at the end.
        song_b_only = _render_tone_transition(
            tmp_path, crossfade_bias=bias, song_a_amplitude=0.0
        )
        end_rms = _rms(song_b_only[-window:])
        assert end_rms > 0.9 * expected_full_gain_rms


def test_gain_and_bias_extremes_stay_finite_and_within_safe_amplitude(
    tmp_path,
) -> None:
    data = _render_tone_transition(
        tmp_path,
        song_a_gain_db=6.0,
        song_b_gain_db=6.0,
        crossfade_bias=1.0,
        song_a_amplitude=0.9,
        song_b_amplitude=0.9,
    )
    assert np.all(np.isfinite(data))
    assert np.max(np.abs(data)) <= 1.0 + 1e-6


def test_song_b_slower_than_song_a_is_sped_up(tmp_path) -> None:
    """Song A=128, Song B=120: Song B must play FASTER (shorter beat period)
    after stretching, i.e. its anchor should land earlier than its original
    unstretched timestamp would suggest relative to Song A's timeline."""
    song_a_bpm, song_b_bpm = 128.0, 120.0
    y_a, sr_a = _make_click_track(song_a_bpm, 20.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 20.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    song_a_anchor = _beat_time(song_a_bpm, 20)
    song_b_anchor = _beat_time(song_b_bpm, 20)

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=song_a_anchor,
        song_b_anchor_seconds=song_b_anchor,
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    mono = data.mean(axis=1)
    _assert_peak_near_center(mono, sr_out, result.duration_seconds)


def test_song_b_faster_than_song_a_is_slowed_down(tmp_path) -> None:
    """Song A=110, Song B=140: Song B must play SLOWER after stretching."""
    song_a_bpm, song_b_bpm = 110.0, 140.0
    y_a, sr_a = _make_click_track(song_a_bpm, 20.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 20.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    song_a_anchor = _beat_time(song_a_bpm, 15)
    song_b_anchor = _beat_time(song_b_bpm, 15)

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=song_a_anchor,
        song_b_anchor_seconds=song_b_anchor,
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    mono = data.mean(axis=1)
    _assert_peak_near_center(mono, sr_out, result.duration_seconds)


def _median_onset_interval(
    mono: np.ndarray, sr: int, tail_fraction: float = 0.75
) -> float | None:
    """Median spacing between detected onsets in the tail of the mixed
    buffer, where the equal-power crossfade has Song B dominating almost
    completely (gain_a ~= 0). This is what actually distinguishes a
    correctly- vs incorrectly-stretched Song B: an anchor beat always ends
    up centered by construction regardless of the stretch rate used, so
    checking *only* alignment can't tell a correct multiplier from a wrong
    one — checking the resulting beat *density* can."""
    tail = mono[int(tail_fraction * len(mono)) :]
    onsets = librosa.onset.onset_detect(y=tail, sr=sr, units="time")
    if len(onsets) < 2:
        return None
    return float(np.median(np.diff(onsets)))


def test_song_b_tempo_multiplier_corrects_half_time_reported_bpm(tmp_path) -> None:
    """Song B's actual recorded pulse matches Song A (128 BPM), but its
    analyzed tempo was (as trackers sometimes do) reported at half that.
    song_b_tempo_multiplier=2 should make the renderer treat it as already
    tempo-matched, so the rendered beat spacing matches Song A's period —
    not needlessly stretch it to some other density."""
    song_a_bpm = 128.0
    reported_song_b_bpm = 64.0
    y_a, sr_a = _make_click_track(song_a_bpm, 20.0)
    y_b, sr_b = _make_click_track(
        song_a_bpm, 20.0
    )  # recorded at the real 128 BPM pulse

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    anchor_seconds = _beat_time(song_a_bpm, 20)

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=anchor_seconds,
        song_b_anchor_seconds=anchor_seconds,
        song_a_bpm=song_a_bpm,
        song_b_bpm=reported_song_b_bpm,
        song_b_tempo_multiplier=2.0,
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    interval = _median_onset_interval(data.mean(axis=1), sr_out)
    assert interval is not None
    assert abs(interval - 60.0 / song_a_bpm) < 0.05


def test_song_b_tempo_multiplier_corrects_double_time_reported_bpm(tmp_path) -> None:
    """Inverse case: Song B's analyzed tempo was reported at double its
    real pulse (256 instead of 128); multiplier=0.5 should correct it."""
    song_a_bpm = 128.0
    reported_song_b_bpm = 256.0
    y_a, sr_a = _make_click_track(song_a_bpm, 20.0)
    y_b, sr_b = _make_click_track(song_a_bpm, 20.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    anchor_seconds = _beat_time(song_a_bpm, 20)

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=anchor_seconds,
        song_b_anchor_seconds=anchor_seconds,
        song_a_bpm=song_a_bpm,
        song_b_bpm=reported_song_b_bpm,
        song_b_tempo_multiplier=0.5,
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    interval = _median_onset_interval(data.mean(axis=1), sr_out)
    assert interval is not None
    assert abs(interval - 60.0 / song_a_bpm) < 0.05


def test_ignoring_the_tempo_multiplier_produces_wrong_beat_density(tmp_path) -> None:
    """Sanity check that the multiplier is actually load-bearing: the same
    misreported-BPM setup *without* correction should clearly NOT produce
    Song A's beat spacing (demonstrating why the correction above matters).
    An anchor beat still lands at the window's center regardless (that's
    guaranteed by construction), so this checks density, not alignment."""
    song_a_bpm = 128.0
    reported_song_b_bpm = 64.0
    y_a, sr_a = _make_click_track(song_a_bpm, 20.0)
    y_b, sr_b = _make_click_track(song_a_bpm, 20.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    anchor_seconds = _beat_time(song_a_bpm, 20)

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=anchor_seconds,
        song_b_anchor_seconds=anchor_seconds,
        song_a_bpm=song_a_bpm,
        song_b_bpm=reported_song_b_bpm,
        song_b_tempo_multiplier=1.0,  # no correction applied
    )

    data, sr_out = sf.read(
        io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True
    )
    interval = _median_onset_interval(data.mean(axis=1), sr_out)
    assert interval is not None
    assert abs(interval - 60.0 / song_a_bpm) > 0.1


def _assert_peak_near_center(
    mono: np.ndarray, sr: int, duration_seconds: float, tolerance_seconds: float = 0.12
) -> None:
    """Anchor-alignment check: the combined energy peak (both tracks'
    anchor beats coinciding) should land within a small tolerance of the
    window's exact center. Phase-vocoder stretching isn't perfectly
    sample-accurate, so this deliberately isn't an exact-sample assertion."""
    center_sample = int(duration_seconds / 2 * sr)
    window = int(tolerance_seconds * sr)
    segment = np.abs(mono[max(0, center_sample - window) : center_sample + window])
    peak_offset = int(np.argmax(segment)) - window
    assert abs(peak_offset / sr) < tolerance_seconds


def test_near_start_anchor_is_padded_not_crashed(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 128.0, 120.0
    y_a, sr_a = _make_click_track(song_a_bpm, 10.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 10.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=0.05,
        song_b_anchor_seconds=0.05,
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    assert np.all(np.isfinite(data))
    expected_samples = round(result.duration_seconds * result.sample_rate)
    assert data.shape[0] == expected_samples


def test_near_end_anchor_is_padded_not_crashed(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 128.0, 120.0
    track_duration = 10.0
    y_a, sr_a = _make_click_track(song_a_bpm, track_duration)
    y_b, sr_b = _make_click_track(song_b_bpm, track_duration)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=track_duration - 0.05,
        song_b_anchor_seconds=track_duration - 0.05,
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    assert np.all(np.isfinite(data))
    expected_samples = round(result.duration_seconds * result.sample_rate)
    assert data.shape[0] == expected_samples


def test_anchor_far_beyond_track_end_still_renders_silently(tmp_path) -> None:
    song_a_bpm, song_b_bpm = 128.0, 120.0
    y_a, sr_a = _make_click_track(song_a_bpm, 5.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 5.0)

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=500.0,
        song_b_anchor_seconds=500.0,
        song_a_bpm=song_a_bpm,
        song_b_bpm=song_b_bpm,
    )

    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    assert np.all(np.isfinite(data))
    assert np.max(np.abs(data)) == 0.0


def test_invalid_bpm_raises_controlled_error(tmp_path) -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)
    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    for bad_bpm in (0.0, -10.0, math.nan, math.inf):
        try:
            render_transition(
                song_a_path=path_a,
                song_b_path=path_b,
                song_a_anchor_seconds=1.0,
                song_b_anchor_seconds=1.0,
                song_a_bpm=bad_bpm,
                song_b_bpm=120.0,
            )
        except TransitionRenderError:
            continue
        raise AssertionError(f"expected TransitionRenderError for bpm={bad_bpm}")


def test_malformed_audio_raises_controlled_error_not_a_crash(tmp_path) -> None:
    path_a = tmp_path / "a.wav"
    path_a.write_bytes(b"not actually audio data" * 50)
    path_b = tmp_path / "b.wav"
    path_b.write_bytes(b"also not audio" * 50)

    try:
        render_transition(
            song_a_path=str(path_a),
            song_b_path=str(path_b),
            song_a_anchor_seconds=1.0,
            song_b_anchor_seconds=1.0,
            song_a_bpm=120.0,
            song_b_bpm=120.0,
        )
        raise AssertionError("expected TransitionRenderError")
    except TransitionRenderError:
        pass


# ---------------------------------------------------------------------------
# HTTP-layer tests — request wiring, validation, and error mapping.
# ---------------------------------------------------------------------------


def _render_plan(
    song_a_bpm: float = 128.0,
    song_b_bpm: float = 120.0,
    song_a_beat: int = 8,
    song_b_beat: int = 8,
) -> str:
    return json.dumps(
        {
            "song_a_anchor": {
                "beat_index": song_a_beat,
                "time_seconds": _beat_time(song_a_bpm, song_a_beat),
            },
            "song_b_anchor": {
                "beat_index": song_b_beat,
                "time_seconds": _beat_time(song_b_bpm, song_b_beat),
            },
            "song_a_bpm": song_a_bpm,
            "song_b_bpm": song_b_bpm,
            "transition_beats": 16,
        }
    )


def test_render_endpoint_returns_playable_wav() -> None:
    song_a_bpm, song_b_bpm = 128.0, 120.0
    y_a, sr_a = _make_click_track(song_a_bpm, 12.0)
    y_b, sr_b = _make_click_track(song_b_bpm, 12.0)

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": _render_plan(song_a_bpm, song_b_bpm)},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert "X-Target-Bpm" in response.headers
    data, _ = sf.read(io.BytesIO(response.content), dtype="float32", always_2d=True)
    assert data.shape[0] > 0


def test_render_endpoint_rejects_missing_song_b() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)

    response = client.post(
        "/transitions/render",
        files={"song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav")},
        data={"plan": _render_plan()},
    )

    assert response.status_code == 422  # FastAPI's required-field validation


def test_render_endpoint_rejects_non_audio_upload() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("notes.txt", b"hello world", "text/plain"),
        },
        data={"plan": _render_plan()},
    )

    assert 400 <= response.status_code < 500


def test_render_endpoint_rejects_malformed_plan_json() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": "not valid json"},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_render_endpoint_rejects_zero_bpm() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    plan = json.loads(_render_plan())
    plan["song_a_bpm"] = 0.0

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": json.dumps(plan)},
    )

    assert response.status_code == 422


def test_render_endpoint_rejects_unsupported_transition_beats() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    plan = json.loads(_render_plan())
    plan["transition_beats"] = 24  # only 8, 16, 32 are supported

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": json.dumps(plan)},
    )

    assert response.status_code == 422


def test_render_endpoint_accepts_each_supported_transition_beats() -> None:
    y_a, sr_a = _make_click_track(128.0, 15.0)
    y_b, sr_b = _make_click_track(120.0, 15.0)

    for beats in (8, 16, 32):
        plan = json.loads(_render_plan())
        plan["transition_beats"] = beats

        response = client.post(
            "/transitions/render",
            files={
                "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
                "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
            },
            data={"plan": json.dumps(plan)},
        )

        assert response.status_code == 200, f"beats={beats} failed: {response.text}"


def test_render_endpoint_rejects_gain_out_of_range() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    for field, value in (
        ("song_a_gain_db", 100.0),
        ("song_a_gain_db", -100.0),
        ("song_b_gain_db", 7.0),
        ("crossfade_bias", 2.0),
        ("crossfade_bias", -2.0),
    ):
        plan = json.loads(_render_plan())
        plan[field] = value

        response = client.post(
            "/transitions/render",
            files={
                "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
                "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
            },
            data={"plan": json.dumps(plan)},
        )

        assert response.status_code == 422, f"{field}={value} should be rejected"


def test_render_endpoint_accepts_gain_and_bias_at_their_limits() -> None:
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    plan = json.loads(_render_plan())
    plan["song_a_gain_db"] = -12.0
    plan["song_b_gain_db"] = 6.0
    plan["crossfade_bias"] = -1.0

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": json.dumps(plan)},
    )

    assert response.status_code == 200


def test_render_endpoint_rejects_malformed_audio_without_500() -> None:
    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", b"not real audio" * 50, "audio/wav"),
            "song_b": ("b.wav", b"also not real audio" * 50, "audio/wav"),
        },
        data={"plan": _render_plan()},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# Bass Swap (M8)
# ---------------------------------------------------------------------------


def _make_dual_band_tone(
    duration: float,
    sr: int = 44100,
    channels: int = 2,
    low_freq: float = 80.0,
    high_freq: float = 4000.0,
    low_amplitude: float = 0.3,
    high_amplitude: float = 0.3,
) -> tuple[np.ndarray, int]:
    """A continuous tone with an independently-controllable low-frequency
    ("bass") component and upper-frequency component, so band-splitting
    and bass-swap behavior can be measured objectively rather than via
    beat timing."""
    n_samples = int(sr * duration)
    t = np.arange(n_samples) / sr
    tone = low_amplitude * np.sin(2 * np.pi * low_freq * t) + high_amplitude * np.sin(
        2 * np.pi * high_freq * t
    )
    y = np.tile(tone.astype(np.float32)[:, None], (1, channels))
    return y, sr


def _render_bass_swap(
    tmp_path,
    *,
    transition_beats: int = 16,
    bass_swap_width_beats: int = 4,
    bass_swap_position: float = 0.5,
    song_a_low_amp: float = 0.3,
    song_a_high_amp: float = 0.0,
    song_b_low_amp: float = 0.3,
    song_b_high_amp: float = 0.0,
    song_a_gain_db: float = 0.0,
    song_b_gain_db: float = 0.0,
    bpm: float = 120.0,
) -> np.ndarray:
    """Renders a bass-swap transition between two continuous same-tempo
    tones (no time-stretching involved) with independently controllable
    low/high content per side, and returns the decoded stereo samples."""
    y_a, sr_a = _make_dual_band_tone(
        10.0, low_amplitude=song_a_low_amp, high_amplitude=song_a_high_amp
    )
    y_b, sr_b = _make_dual_band_tone(
        10.0, low_amplitude=song_b_low_amp, high_amplitude=song_b_high_amp
    )

    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=5.0,
        song_b_anchor_seconds=5.0,
        song_a_bpm=bpm,
        song_b_bpm=bpm,
        transition_beats=transition_beats,
        song_a_gain_db=song_a_gain_db,
        song_b_gain_db=song_b_gain_db,
        transition_style="bass_swap",
        bass_swap_position=bass_swap_position,
        bass_swap_width_beats=bass_swap_width_beats,
    )
    data, _ = sf.read(io.BytesIO(result.wav_bytes), dtype="float32", always_2d=True)
    return data


def _crossover_x(
    n: int, transition_beats: int, bass_swap_width_beats: int, position: float
) -> float:
    gain_a, gain_b = _bass_swap_gains(
        n,
        transition_beats=transition_beats,
        bass_swap_width_beats=bass_swap_width_beats,
        bass_swap_position=position,
    )
    return int(np.argmin(np.abs(gain_a - gain_b))) / n


def _transition_zone_width(
    n: int, transition_beats: int, bass_swap_width_beats: int, position: float = 0.5
) -> int:
    gain_a, _ = _bass_swap_gains(
        n,
        transition_beats=transition_beats,
        bass_swap_width_beats=bass_swap_width_beats,
        bass_swap_position=position,
    )
    in_zone = (gain_a > 1e-6) & (gain_a < 1 - 1e-6)
    return int(np.sum(in_zone))


def test_smooth_style_matches_the_original_full_band_crossfade(tmp_path) -> None:
    # item 1: explicit transition_style="smooth" must render byte-identical
    # output to the M7 default (no style argument at all).
    y_a, sr_a = _make_click_track(128.0, 12.0)
    y_b, sr_b = _make_click_track(120.0, 12.0)
    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    kwargs = {
        "song_a_path": path_a,
        "song_b_path": path_b,
        "song_a_anchor_seconds": _beat_time(128.0, 10),
        "song_b_anchor_seconds": _beat_time(120.0, 10),
        "song_a_bpm": 128.0,
        "song_b_bpm": 120.0,
    }
    default_result = render_transition(**kwargs)
    explicit_smooth_result = render_transition(**kwargs, transition_style="smooth")

    assert default_result.wav_bytes == explicit_smooth_result.wav_bytes


def test_smooth_does_not_require_or_use_bass_specific_settings(tmp_path) -> None:
    # item 2: nonsensical/invalid bass settings must not affect (or block)
    # a smooth render, since smooth never reads them.
    y_a, sr_a = _make_click_track(128.0, 10.0)
    y_b, sr_b = _make_click_track(120.0, 10.0)
    path_a = _write_temp(tmp_path, "a.wav", _wav_bytes(y_a, sr_a))
    path_b = _write_temp(tmp_path, "b.wav", _wav_bytes(y_b, sr_b))

    result = render_transition(
        song_a_path=path_a,
        song_b_path=path_b,
        song_a_anchor_seconds=_beat_time(128.0, 8),
        song_b_anchor_seconds=_beat_time(120.0, 8),
        song_a_bpm=128.0,
        song_b_bpm=120.0,
        transition_style="smooth",
        bass_swap_position=0.99,  # invalid for width=8/beats=8, ignored anyway
        bass_swap_width_beats=8,
        transition_beats=8,
    )
    assert len(result.wav_bytes) > 0


def test_bass_split_produces_finite_output() -> None:
    y, _ = _make_dual_band_tone(3.0)
    low, upper = _split_frequency_bands(y)
    assert np.all(np.isfinite(low))
    assert np.all(np.isfinite(upper))


def test_bass_split_reconstructs_the_original_signal() -> None:
    y, _ = _make_dual_band_tone(3.0)
    low, upper = _split_frequency_bands(y)
    assert np.max(np.abs((low + upper) - y)) < 1e-4


def test_bass_split_preserves_stereo() -> None:
    y, _ = _make_dual_band_tone(3.0, channels=2)
    low, upper = _split_frequency_bands(y)
    assert low.shape[1] == 2
    assert upper.shape[1] == 2


def test_bass_split_on_a_very_short_buffer_stays_finite_and_reconstructs() -> None:
    y, _ = _make_dual_band_tone(0.002)  # a handful of samples
    low, upper = _split_frequency_bands(y)
    assert np.all(np.isfinite(low))
    assert np.all(np.isfinite(upper))
    assert np.max(np.abs((low + upper) - y)) < 1e-3


def test_song_a_bass_energy_dominates_before_the_swap(tmp_path) -> None:
    # item 6: Song B contributes no bass at all, so any bass energy in the
    # output is Song A's — it should be strong near the start and have
    # faded away by the end.
    data = _render_bass_swap(tmp_path, song_a_low_amp=0.3, song_b_low_amp=0.0)
    low, _ = _split_frequency_bands(data)
    n = low.shape[0]
    early = _rms(low[: n // 20])
    late = _rms(low[-n // 20 :])
    assert early > late * 5


def test_song_b_bass_energy_dominates_after_the_swap(tmp_path) -> None:
    # item 7: mirror of the above, isolating Song B's bass.
    data = _render_bass_swap(tmp_path, song_a_low_amp=0.0, song_b_low_amp=0.3)
    low, _ = _split_frequency_bands(data)
    n = low.shape[0]
    early = _rms(low[: n // 20])
    late = _rms(low[-n // 20 :])
    assert late > early * 5


def test_bass_ownership_crossover_occurs_near_the_configured_position() -> None:
    # item 8
    n = 20000
    for position in (0.3, 0.5, 0.7):
        crossover = _crossover_x(n, 16, 4, position)
        assert abs(crossover - position) < 0.01


def test_two_beat_width_produces_a_tighter_swap_than_four_beats() -> None:
    # item 9
    n = 100000
    two_beats = _transition_zone_width(n, transition_beats=16, bass_swap_width_beats=2)
    four_beats = _transition_zone_width(n, transition_beats=16, bass_swap_width_beats=4)
    assert two_beats < four_beats


def test_four_beat_width_produces_a_tighter_swap_than_eight_beats() -> None:
    # item 10
    n = 100000
    four_beats = _transition_zone_width(n, transition_beats=32, bass_swap_width_beats=4)
    eight_beats = _transition_zone_width(
        n, transition_beats=32, bass_swap_width_beats=8
    )
    assert four_beats < eight_beats


def test_earlier_position_moves_the_bass_crossover_earlier() -> None:
    # item 11
    n = 20000
    reference = _crossover_x(n, 16, 4, 0.5)
    earlier = _crossover_x(n, 16, 4, 0.3)
    assert earlier < reference


def test_later_position_moves_the_bass_crossover_later() -> None:
    # item 12
    n = 20000
    reference = _crossover_x(n, 16, 4, 0.5)
    later = _crossover_x(n, 16, 4, 0.7)
    assert later > reference


def test_song_b_bass_gain_is_effectively_zero_at_transition_start() -> None:
    # item 13: bass_swap_position=0.125 is the earliest valid position for
    # a 4-beat swap within a 16-beat transition (see _valid_bass_swap_range).
    gain_a, gain_b = _bass_swap_gains(
        1000, transition_beats=16, bass_swap_width_beats=4, bass_swap_position=0.125
    )
    assert gain_b[0] < 0.01
    assert gain_a[0] > 0.99


def test_song_a_bass_gain_is_effectively_zero_at_transition_end() -> None:
    # item 14: the latest valid position for the same window.
    gain_a, gain_b = _bass_swap_gains(
        1000, transition_beats=16, bass_swap_width_beats=4, bass_swap_position=0.875
    )
    assert gain_a[-1] < 0.01
    assert gain_b[-1] > 0.99


def test_upper_band_follows_the_main_crossfade_not_the_bass_envelope(tmp_path) -> None:
    # item 15: Song B is entirely silent, and Song A contributes only
    # upper-band content. The tight bass envelope (position=0.2, width=4
    # beats of 16) would already be fully switched to (silent) Song B well
    # before the window's midpoint. If the upper band were wrongly driven
    # by that envelope, its RMS at the midpoint would have collapsed to
    # ~0; the main crossfade instead still has Song A near cos(pi/4).
    data = _render_bass_swap(
        tmp_path,
        song_a_low_amp=0.0,
        song_a_high_amp=0.3,
        song_b_low_amp=0.0,
        song_b_high_amp=0.0,
        bass_swap_position=0.2,
        bass_swap_width_beats=4,
        transition_beats=16,
    )
    _, upper = _split_frequency_bands(data)
    n = upper.shape[0]
    mid_rms = _rms(upper[n // 2 - 200 : n // 2 + 200])
    expected_main_crossfade_rms = 0.3 * math.cos(math.pi / 4) / math.sqrt(2)
    assert mid_rms > 0.5 * expected_main_crossfade_rms


def test_gain_trim_scales_low_and_upper_bands_consistently(tmp_path) -> None:
    # item 16
    baseline = _render_bass_swap(
        tmp_path,
        song_a_low_amp=0.2,
        song_a_high_amp=0.2,
        song_b_low_amp=0.0,
        song_b_high_amp=0.0,
        song_a_gain_db=0.0,
    )
    boosted = _render_bass_swap(
        tmp_path,
        song_a_low_amp=0.2,
        song_a_high_amp=0.2,
        song_b_low_amp=0.0,
        song_b_high_amp=0.0,
        song_a_gain_db=6.0,
    )

    low_base, upper_base = _split_frequency_bands(baseline)
    low_boost, upper_boost = _split_frequency_bands(boosted)

    early = slice(0, 2000)  # near the very start: bass and main gain_a ~= 1
    low_ratio = _rms(low_boost[early]) / _rms(low_base[early])
    upper_ratio = _rms(upper_boost[early]) / _rms(upper_base[early])

    expected_ratio = 10 ** (6.0 / 20)
    assert abs(low_ratio - expected_ratio) < 0.1
    assert abs(upper_ratio - expected_ratio) < 0.1


def test_bass_swap_output_is_finite_and_within_safe_amplitude(tmp_path) -> None:
    # items 21/22, for the bass-swap path specifically
    data = _render_bass_swap(
        tmp_path,
        song_a_low_amp=0.9,
        song_a_high_amp=0.9,
        song_b_low_amp=0.9,
        song_b_high_amp=0.9,
    )
    assert np.all(np.isfinite(data))
    assert np.max(np.abs(data)) <= 1.0 + 1e-6


def test_render_endpoint_rejects_invalid_transition_style() -> None:
    # item 17
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    plan = json.loads(_render_plan())
    plan["transition_style"] = "reverb_swap"

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": json.dumps(plan)},
    )

    assert response.status_code == 422


def test_render_endpoint_rejects_invalid_bass_width() -> None:
    # item 18
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    plan = json.loads(_render_plan())
    plan["transition_style"] = "bass_swap"
    plan["bass_swap_width_beats"] = 3  # only 2, 4, 8 are supported

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": json.dumps(plan)},
    )

    assert response.status_code == 422


def test_render_endpoint_rejects_bass_swap_position_outside_valid_window() -> None:
    # item 19
    y_a, sr_a = _make_click_track(128.0, 5.0)
    y_b, sr_b = _make_click_track(120.0, 5.0)

    plan = json.loads(_render_plan())
    plan["transition_beats"] = 16
    plan["transition_style"] = "bass_swap"
    plan["bass_swap_width_beats"] = 4
    plan["bass_swap_position"] = 0.05  # valid range is 0.125-0.875

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
            "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
        },
        data={"plan": json.dumps(plan)},
    )

    assert response.status_code == 422


def test_render_endpoint_accepts_bass_swap_at_each_transition_length() -> None:
    # item 20
    y_a, sr_a = _make_click_track(128.0, 15.0)
    y_b, sr_b = _make_click_track(120.0, 15.0)

    for beats, width in ((8, 2), (16, 4), (32, 8)):
        plan = json.loads(_render_plan())
        plan["transition_beats"] = beats
        plan["transition_style"] = "bass_swap"
        plan["bass_swap_width_beats"] = width
        plan["bass_swap_position"] = 0.5

        response = client.post(
            "/transitions/render",
            files={
                "song_a": ("a.wav", _wav_bytes(y_a, sr_a), "audio/wav"),
                "song_b": ("b.wav", _wav_bytes(y_b, sr_b), "audio/wav"),
            },
            data={"plan": json.dumps(plan)},
        )

        assert response.status_code == 200, (
            f"beats={beats} width={width} failed: {response.text}"
        )
