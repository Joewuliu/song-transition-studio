from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _beats(bpm: float, count: int) -> list[float]:
    period = 60.0 / bpm
    return [round(i * period, 3) for i in range(count)]


def _candidate(beat_index: int, time_seconds: float, score: float = 1.0) -> dict:
    return {
        "beat_index": beat_index,
        "time_seconds": time_seconds,
        "score": score,
        "boundary_strength": 0.5,
        "energy_before": 0.1,
        "energy_after": 0.2,
    }


def _analysis(
    bpm: float,
    beat_count: int,
    *,
    exit_candidates: list[dict] | None = None,
    entry_candidates: list[dict] | None = None,
) -> dict:
    beats = _beats(bpm, beat_count)
    return {
        "duration_seconds": beats[-1] + 60.0 / bpm,
        "tempo_bpm": bpm,
        "beat_count": len(beats),
        "beats": beats,
        "entry_candidates": entry_candidates or [],
        "exit_candidates": exit_candidates or [],
    }


def test_suggest_endpoint_requires_no_audio_upload_and_returns_a_plan() -> None:
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    assert response.status_code == 200
    body = response.json()

    plan = body["plan"]
    assert plan["song_a_anchor"]["beat_index"] == 150
    assert plan["song_b_anchor"]["beat_index"] == 10
    assert plan["transition_beats"] in (8, 16, 32)
    assert plan["song_b_tempo_multiplier"] in (0.5, 1, 2)
    assert -12.0 <= plan["song_a_gain_db"] <= 6.0
    assert -12.0 <= plan["song_b_gain_db"] <= 6.0
    assert -1.0 <= plan["crossfade_bias"] <= 1.0

    assert body["tempo_compatibility"] in (
        "compatible",
        "moderate",
        "significant",
        "extreme",
    )
    assert isinstance(body["used_tempo_normalization"], bool)
    assert body["song_a_anchor_source"] in ("candidate", "fallback")
    assert body["song_b_anchor_source"] in ("candidate", "fallback")


def test_suggest_endpoint_response_matches_the_frontend_transition_plan_shape() -> None:
    """The suggested plan's keys must be exactly what TransitionPlan needs
    (plus the tempo multiplier) — no extra required editable fields."""
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    plan = response.json()["plan"]
    assert set(plan.keys()) == {
        "song_a_anchor",
        "song_b_anchor",
        "transition_beats",
        "song_a_gain_db",
        "song_b_gain_db",
        "crossfade_bias",
        "song_b_tempo_multiplier",
        "transition_style",
        "bass_swap_position",
        "bass_swap_width_beats",
    }


def test_suggest_endpoint_detects_half_double_time_relationship() -> None:
    song_a = _analysis(140.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(70.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    body = response.json()
    assert body["plan"]["song_b_tempo_multiplier"] == 2
    assert body["effective_song_b_bpm"] == 140.0
    assert body["used_tempo_normalization"] is True


def test_suggest_endpoint_rejects_track_with_no_beats() -> None:
    song_a = {
        "duration_seconds": 0.0,
        "tempo_bpm": 0.0,
        "beat_count": 0,
        "beats": [],
        "entry_candidates": [],
        "exit_candidates": [],
    }
    song_b = _analysis(120.0, 200)

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_suggest_endpoint_rejects_malformed_request_body() -> None:
    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": {"not": "a valid analysis"}},
    )

    assert response.status_code == 422


def test_suggest_endpoint_still_returns_the_existing_suggestion_plan() -> None:
    """item 15: the M9 `variants` addition must not disturb the pre-M9
    top-level `plan` and its metadata."""
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    body = response.json()
    assert body["plan"]["song_a_anchor"]["beat_index"] == 150
    assert body["plan"]["song_b_anchor"]["beat_index"] == 10
    assert body["plan"]["transition_style"] == "smooth"
    assert "harmonic_compatibility" in body
    assert "tempo_compatibility" in body


def test_suggest_endpoint_returns_the_three_expected_variants() -> None:
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    variants = response.json()["variants"]
    assert [variant["id"] for variant in variants] == ["smooth", "bass_swap", "quick"]
    for variant in variants:
        assert set(variant.keys()) == {"id", "name", "description", "plan"}
        assert variant["plan"]["song_a_anchor"]["beat_index"] == 150
        assert variant["plan"]["song_b_anchor"]["beat_index"] == 10
