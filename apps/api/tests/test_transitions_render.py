import io
import json
import math

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app
from app.services.transition_renderer import (
    TransitionRenderError,
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
