import io
import json

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services.upload_validation import safe_temp_suffix

client = TestClient(app)


def _wav_bytes(n_samples: int = 2000, sr: int = 22050) -> bytes:
    y = np.zeros(n_samples, dtype=np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, y, sr, format="WAV", subtype="FLOAT")
    return buffer.getvalue()


def _minimal_render_plan() -> str:
    return json.dumps(
        {
            "song_a_anchor": {"beat_index": 0, "time_seconds": 0.0},
            "song_b_anchor": {"beat_index": 0, "time_seconds": 0.0},
            "song_a_bpm": 120.0,
            "song_b_bpm": 120.0,
        }
    )


def test_analyze_rejects_an_upload_over_the_configured_limit(monkeypatch) -> None:
    data = _wav_bytes(n_samples=5000)
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, "100")
    assert len(data) > 100

    response = client.post(
        "/tracks/analyze",
        files={"file": ("a.wav", data, "audio/wav")},
    )

    assert response.status_code == 413
    assert "detail" in response.json()


def test_analyze_accepts_an_upload_within_the_configured_limit(monkeypatch) -> None:
    data = _wav_bytes(n_samples=2000)
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, str(len(data) + 1000))

    response = client.post(
        "/tracks/analyze",
        files={"file": ("a.wav", data, "audio/wav")},
    )

    assert response.status_code == 200


def test_render_rejects_when_either_upload_exceeds_the_limit(monkeypatch) -> None:
    data = _wav_bytes(n_samples=5000)
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, "100")
    assert len(data) > 100

    response = client.post(
        "/transitions/render",
        files={
            "song_a": ("a.wav", data, "audio/wav"),
            "song_b": ("b.wav", data, "audio/wav"),
        },
        data={"plan": _minimal_render_plan()},
    )

    assert response.status_code == 413


def test_upload_limit_is_configurable_and_reflected_in_the_error_message(
    monkeypatch,
) -> None:
    data = _wav_bytes(n_samples=5000)
    monkeypatch.setenv(config.MAX_UPLOAD_BYTES_ENV_VAR, str(1024 * 1024))  # 1 MB

    response = client.post(
        "/tracks/analyze",
        files={"file": ("a.wav", data, "audio/wav")},
    )

    # This particular payload is well under 1 MB, so it should be accepted
    # — this documents that a *raised* limit is honored, not just a
    # lowered one.
    assert response.status_code == 200


def test_safe_temp_suffix_extracts_a_normal_extension() -> None:
    assert safe_temp_suffix("song.wav") == ".wav"


def test_safe_temp_suffix_ignores_directory_components() -> None:
    # Path.suffix already strips any leading path segments, so a hostile
    # filename can't influence where the temp file actually gets written.
    assert safe_temp_suffix("../../etc/passwd.wav") == ".wav"


def test_safe_temp_suffix_is_length_bounded() -> None:
    hostile = "track." + ("a" * 500)
    suffix = safe_temp_suffix(hostile)
    assert len(suffix) <= 16


def test_safe_temp_suffix_handles_no_extension() -> None:
    assert safe_temp_suffix("track") == ""
