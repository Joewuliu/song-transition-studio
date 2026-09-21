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


def test_suggest_endpoint_requires_no_audio_upload_and_returns_choices() -> None:
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    assert response.status_code == 200
    body = response.json()

    assert len(body["choices"]) >= 1
    plan = body["choices"][0]["plan"]
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
    """Each choice's plan keys must be exactly what TransitionPlan needs
    (plus the tempo multiplier) — no extra required editable fields."""
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    plan = response.json()["choices"][0]["plan"]
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


def test_suggest_endpoint_choice_shape() -> None:
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    for choice in response.json()["choices"]:
        assert set(choice.keys()) == {
            "id",
            "label",
            "description",
            "plan",
            "compatibility",
            "harmonic_compatibility",
            "song_a_local_key",
            "song_a_local_mode",
            "song_b_local_key",
            "song_b_local_mode",
        }
        assert 0.0 <= choice["compatibility"] <= 1.0
        assert 0.0 <= choice["harmonic_compatibility"] <= 1.0


def test_suggest_endpoint_detects_half_double_time_relationship() -> None:
    song_a = _analysis(140.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(70.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    body = response.json()
    assert body["choices"][0]["plan"]["song_b_tempo_multiplier"] == 2
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


def test_suggest_endpoint_choices_share_the_same_global_transition_style() -> None:
    song_a = _analysis(128.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    body = response.json()
    for choice in body["choices"]:
        assert choice["plan"]["transition_style"] == "smooth"


def test_suggest_endpoint_returns_multiple_distinct_choices_for_a_wide_pool() -> None:
    exits = [
        _candidate(60 + i * 6, 30.0 + i * 3.0, score=0.5 + 0.05 * i) for i in range(8)
    ]
    entries = [
        _candidate(5 + i * 5, 2.5 + i * 2.5, score=0.5 + 0.04 * i) for i in range(8)
    ]
    song_a = _analysis(128.0, 300, exit_candidates=exits)
    song_b = _analysis(120.0, 300, entry_candidates=entries)

    response = client.post(
        "/transitions/suggest",
        json={"song_a_analysis": song_a, "song_b_analysis": song_b},
    )

    body = response.json()
    assert len(body["choices"]) == 3
    ids = [choice["id"] for choice in body["choices"]]
    assert ids == ["1", "2", "3"]
    anchor_pairs = {
        (
            choice["plan"]["song_a_anchor"]["beat_index"],
            choice["plan"]["song_b_anchor"]["beat_index"],
        )
        for choice in body["choices"]
    }
    assert len(anchor_pairs) == 3  # genuinely different anchor pairs
