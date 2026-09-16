import io
import math

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _wav_bytes(y: np.ndarray, sr: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, y, sr, format="WAV")
    return buffer.getvalue()


def _make_click_track(bpm: float, duration: float, sr: int = 22050) -> bytes:
    """A synthetic percussive click track at an exact, known BPM."""
    interval = 60.0 / bpm
    n_samples = int(sr * duration)
    y = np.zeros(n_samples, dtype=np.float32)

    click_len = int(sr * 0.01)
    click = (
        np.sin(2 * np.pi * 1000 * np.arange(click_len) / sr) * np.hanning(click_len)
    ).astype(np.float32)

    t = 0.0
    while t < duration:
        start = int(t * sr)
        end = min(start + click_len, n_samples)
        y[start:end] += click[: end - start]
        t += interval

    return _wav_bytes(y, sr)


def _make_silence(duration: float, sr: int = 22050) -> bytes:
    y = np.zeros(int(sr * duration), dtype=np.float32)
    return _wav_bytes(y, sr)


def test_health_still_works() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_wav_is_accepted_with_correct_schema() -> None:
    audio = _make_click_track(bpm=100.0, duration=5.0)

    response = client.post(
        "/tracks/analyze",
        files={"file": ("track.wav", audio, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == {
        "duration_seconds",
        "tempo_bpm",
        "beat_count",
        "beats",
        "entry_candidates",
        "exit_candidates",
    }
    assert isinstance(body["duration_seconds"], (int, float))
    assert isinstance(body["tempo_bpm"], (int, float))
    assert isinstance(body["beat_count"], int)
    assert isinstance(body["beats"], list)
    assert isinstance(body["entry_candidates"], list)
    assert isinstance(body["exit_candidates"], list)


def test_duration_is_reasonable() -> None:
    audio = _make_click_track(bpm=90.0, duration=6.0)

    response = client.post(
        "/tracks/analyze",
        files={"file": ("track.wav", audio, "audio/wav")},
    )

    assert response.status_code == 200
    duration = response.json()["duration_seconds"]
    assert math.isfinite(duration)
    assert abs(duration - 6.0) < 0.1


def test_tempo_is_finite_and_non_negative() -> None:
    audio = _make_silence(duration=3.0)

    response = client.post(
        "/tracks/analyze",
        files={"file": ("silence.wav", audio, "audio/wav")},
    )

    assert response.status_code == 200
    tempo = response.json()["tempo_bpm"]
    assert math.isfinite(tempo)
    assert tempo >= 0


def test_beats_are_finite_ascending_and_match_beat_count() -> None:
    audio = _make_click_track(bpm=128.0, duration=8.0)

    response = client.post(
        "/tracks/analyze",
        files={"file": ("track.wav", audio, "audio/wav")},
    )

    assert response.status_code == 200
    body = response.json()
    beats = body["beats"]

    assert all(math.isfinite(t) for t in beats)
    assert beats == sorted(beats)
    assert body["beat_count"] == len(beats)


def test_known_bpm_click_track_is_estimated_within_tolerance() -> None:
    audio = _make_click_track(bpm=120.0, duration=10.0)

    response = client.post(
        "/tracks/analyze",
        files={"file": ("track.wav", audio, "audio/wav")},
    )

    assert response.status_code == 200
    tempo = response.json()["tempo_bpm"]

    # Beat trackers commonly land on the true tempo or a half/double-time
    # multiple of it; accept any of those within a reasonable tolerance
    # rather than pinning an exact value.
    candidates = (120.0, 60.0, 240.0)
    assert any(abs(tempo - candidate) < 15 for candidate in candidates)


def test_non_audio_file_is_rejected_with_4xx() -> None:
    response = client.post(
        "/tracks/analyze",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert 400 <= response.status_code < 500
    assert "detail" in response.json()


def test_malformed_audio_returns_controlled_error_not_500() -> None:
    garbage = b"this is not a real wav file" * 100

    response = client.post(
        "/tracks/analyze",
        files={"file": ("track.wav", garbage, "audio/wav")},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_missing_file_is_rejected() -> None:
    response = client.post("/tracks/analyze")

    assert response.status_code == 422  # FastAPI's own missing-field validation


def test_empty_file_is_rejected() -> None:
    response = client.post(
        "/tracks/analyze",
        files={"file": ("track.wav", b"", "audio/wav")},
    )

    assert response.status_code == 400
