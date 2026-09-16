from app.schemas import TrackAnalysis, TransitionCandidate
from app.services.transition_planner import (
    TransitionPlannerError,
    suggest_transition_plan,
)


def _beats(bpm: float, count: int) -> list[float]:
    period = 60.0 / bpm
    return [round(i * period, 3) for i in range(count)]


def _analysis(
    bpm: float,
    beat_count: int,
    *,
    exit_candidates: list[TransitionCandidate] | None = None,
    entry_candidates: list[TransitionCandidate] | None = None,
) -> TrackAnalysis:
    beats = _beats(bpm, beat_count)
    duration = beats[-1] + 60.0 / bpm
    return TrackAnalysis(
        duration_seconds=duration,
        tempo_bpm=bpm,
        beat_count=len(beats),
        beats=beats,
        entry_candidates=entry_candidates or [],
        exit_candidates=exit_candidates or [],
    )


def _candidate(
    beat_index: int,
    time_seconds: float,
    score: float,
    *,
    energy_before: float = 0.1,
    energy_after: float = 0.2,
    local_key: str | None = None,
    local_mode: str | None = None,
    local_key_confidence: float = 0.0,
) -> TransitionCandidate:
    return TransitionCandidate(
        beat_index=beat_index,
        time_seconds=time_seconds,
        score=score,
        boundary_strength=0.5,
        energy_before=energy_before,
        energy_after=energy_after,
        local_key=local_key,
        local_mode=local_mode,
        local_key_confidence=local_key_confidence,
    )


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def test_no_candidates_falls_back_near_75_percent_for_song_a() -> None:
    song_a = _analysis(120.0, 200)
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    expected_target = 0.75 * song_a.duration_seconds
    nearest = min(song_a.beats, key=lambda t: abs(t - expected_target))
    assert result.song_a_anchor.time_seconds == nearest
    assert result.song_a_anchor.from_candidate is False


def test_no_candidates_falls_back_near_15_percent_for_song_b() -> None:
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200)

    result = suggest_transition_plan(song_a, song_b)

    expected_target = 0.15 * song_b.duration_seconds
    nearest = min(song_b.beats, key=lambda t: abs(t - expected_target))
    assert result.song_b_anchor.time_seconds == nearest
    assert result.song_b_anchor.from_candidate is False


def test_fallback_anchor_is_an_actual_detected_beat() -> None:
    song_a = _analysis(120.0, 50)
    song_b = _analysis(120.0, 50)

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_anchor.time_seconds in song_a.beats
    assert result.song_b_anchor.time_seconds in song_b.beats


def test_missing_beats_raises_planner_error() -> None:
    song_a = TrackAnalysis(duration_seconds=0.0, tempo_bpm=0.0, beat_count=0, beats=[])
    song_b = _analysis(120.0, 50)

    try:
        suggest_transition_plan(song_a, song_b)
        raise AssertionError("expected TransitionPlannerError")
    except TransitionPlannerError:
        pass


# ---------------------------------------------------------------------------
# Candidate preference
# ---------------------------------------------------------------------------


def test_song_a_prefers_highest_scoring_exit_candidate() -> None:
    candidates = [
        _candidate(50, 25.0, 0.4),
        _candidate(90, 45.0, 0.9),
        _candidate(70, 35.0, 0.6),
    ]
    song_a = _analysis(120.0, 200, exit_candidates=candidates)
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(5, 2.5, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_anchor.beat_index == 90
    assert result.song_a_anchor.from_candidate is True


def test_song_b_prefers_highest_scoring_entry_candidate() -> None:
    candidates = [
        _candidate(5, 2.5, 0.3),
        _candidate(20, 10.0, 0.9),
        _candidate(15, 7.5, 0.5),
    ]
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=candidates)

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_b_anchor.beat_index == 20
    assert result.song_b_anchor.from_candidate is True


def test_pairwise_prefers_better_harmony_over_slightly_higher_score() -> None:
    """Exit candidates: a slightly-higher-scoring one in a harmonically
    distant key (F#, a tritone from the entry's C) vs a slightly-lower-
    scoring one that shares the entry's exact key. The combined pair score
    should prefer the harmonically compatible pair."""
    exit_strong_score_poor_harmony = _candidate(
        50, 25.0, 0.9, local_key="F#", local_mode="major"
    )
    exit_weaker_score_great_harmony = _candidate(
        70, 35.0, 0.8, local_key="C", local_mode="major"
    )
    entry = _candidate(10, 5.0, 0.8, local_key="C", local_mode="major")

    song_a = _analysis(
        120.0,
        200,
        exit_candidates=[
            exit_strong_score_poor_harmony,
            exit_weaker_score_great_harmony,
        ],
    )
    song_b = _analysis(120.0, 200, entry_candidates=[entry])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_anchor.beat_index == 70
    assert result.harmonic_compatibility == 1.0


def test_harmony_cannot_make_a_terrible_candidate_beat_a_much_stronger_one() -> None:
    """A terrible-scoring exit candidate with perfect harmony must not beat
    a much stronger exit candidate that merely has poor harmony — harmony
    is weighted low enough (0.2) that it can't dominate a large quality gap
    (0.9 vs 0.05, i.e. 0.4 * 0.85 = 0.34 potential swing, versus harmony's
    maximum possible swing of only 0.2 * 1.0 = 0.2)."""
    exit_terrible_perfect_harmony = _candidate(
        50, 25.0, 0.05, local_key="C", local_mode="major"
    )
    exit_excellent_poor_harmony = _candidate(
        70, 35.0, 0.95, local_key="F#", local_mode="major"
    )
    entry = _candidate(10, 5.0, 0.8, local_key="C", local_mode="major")

    song_a = _analysis(
        120.0,
        200,
        exit_candidates=[exit_terrible_perfect_harmony, exit_excellent_poor_harmony],
    )
    song_b = _analysis(120.0, 200, entry_candidates=[entry])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_anchor.beat_index == 70


def test_pairwise_harmony_is_computed_from_the_selected_pair_specifically() -> None:
    """Different Song B candidates imply different best Song A pairings —
    confirms the planner truly evaluates pairs jointly, not each side's
    single best candidate independently."""
    exit_c_major = _candidate(50, 25.0, 0.8, local_key="C", local_mode="major")
    exit_g_major = _candidate(70, 35.0, 0.8, local_key="G", local_mode="major")
    song_a = _analysis(120.0, 200, exit_candidates=[exit_c_major, exit_g_major])

    entry_matches_c = _candidate(10, 5.0, 0.8, local_key="C", local_mode="major")
    song_b_prefers_c = _analysis(120.0, 200, entry_candidates=[entry_matches_c])
    result_c = suggest_transition_plan(song_a, song_b_prefers_c)
    assert result_c.song_a_anchor.beat_index == 50  # C major pairs perfectly with C

    entry_matches_g = _candidate(10, 5.0, 0.8, local_key="G", local_mode="major")
    song_b_prefers_g = _analysis(120.0, 200, entry_candidates=[entry_matches_g])
    result_g = suggest_transition_plan(song_a, song_b_prefers_g)
    assert result_g.song_a_anchor.beat_index == 70  # G major pairs perfectly with G


def test_suggested_anchors_are_members_of_the_beats_array() -> None:
    song_a = _analysis(120.0, 300, exit_candidates=[_candidate(200, 100.0, 1.0)])
    song_b = _analysis(120.0, 300, entry_candidates=[_candidate(20, 10.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_anchor.time_seconds in song_a.beats
    assert result.song_b_anchor.time_seconds in song_b.beats


# ---------------------------------------------------------------------------
# Half/double-time tempo multiplier
# ---------------------------------------------------------------------------


def test_140_bpm_a_and_70_bpm_b_chooses_double_multiplier() -> None:
    song_a = _analysis(140.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(70.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_b_tempo_multiplier == 2.0
    assert result.effective_song_b_bpm == 140.0


def test_70_bpm_a_and_140_bpm_b_chooses_half_multiplier() -> None:
    song_a = _analysis(70.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(140.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_b_tempo_multiplier == 0.5
    assert result.effective_song_b_bpm == 70.0


def test_similar_bpms_choose_multiplier_one() -> None:
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(124.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_b_tempo_multiplier == 1.0
    assert result.effective_song_b_bpm == 124.0


def test_raw_bpm_is_never_overwritten_by_the_multiplier() -> None:
    """The multiplier only scales what the renderer treats as Song B's
    tempo — the analysis's own tempo_bpm must stay untouched by the
    planner (the UI keeps showing the raw detected value separately)."""
    song_a = _analysis(140.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(70.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    suggest_transition_plan(song_a, song_b)

    assert song_b.tempo_bpm == 70.0


# ---------------------------------------------------------------------------
# Transition length / tempo-compatibility category
# ---------------------------------------------------------------------------


def test_very_compatible_tempo_prefers_32_beats() -> None:
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(121.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.transition_beats == 32
    assert result.tempo_compatibility == "compatible"


def test_moderate_mismatch_chooses_16_beats() -> None:
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(108.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.transition_beats == 16
    assert result.tempo_compatibility == "moderate"


def test_larger_acceptable_mismatch_chooses_8_beats() -> None:
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(95.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.transition_beats == 8
    assert result.tempo_compatibility == "significant"


def test_extreme_mismatch_produces_compatibility_warning() -> None:
    # Even after choosing the best of {0.5x, 1x, 2x}, this pairing sits
    # close to the worst-case midpoint between two candidate multipliers.
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(82.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.tempo_compatibility == "extreme"
    assert result.transition_beats == 8  # still a usable suggestion, not a block


def test_invalid_bpm_raises_planner_error() -> None:
    song_a = _analysis(120.0, 200)
    song_a = song_a.model_copy(update={"tempo_bpm": 0.0})
    song_b = _analysis(120.0, 200)

    try:
        suggest_transition_plan(song_a, song_b)
        raise AssertionError("expected TransitionPlannerError")
    except TransitionPlannerError:
        pass


# ---------------------------------------------------------------------------
# Gain suggestion
# ---------------------------------------------------------------------------


def test_gain_suggestion_stays_within_allowed_bounds() -> None:
    # Song A is loud right before its anchor, Song B is very quiet right
    # after its anchor — Song B should be suggested *louder* to compensate,
    # clamped at the configured limit rather than boosted without bound.
    loud_exit = _candidate(150, 75.0, 1.0, energy_before=0.9, energy_after=0.9)
    quiet_entry = _candidate(10, 5.0, 1.0, energy_before=0.001, energy_after=0.001)

    song_a = _analysis(120.0, 200, exit_candidates=[loud_exit])
    song_b = _analysis(120.0, 200, entry_candidates=[quiet_entry])

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_gain_db == 0.0
    assert -6.0 <= result.song_b_gain_db <= 6.0
    # The gap here is large enough that the suggestion should hit (not just
    # respect) the clamp — confirms the clamp is actually exercised.
    assert result.song_b_gain_db == 6.0


def test_gain_suggestion_defaults_to_zero_without_candidate_energy_data() -> None:
    song_a = _analysis(120.0, 200)
    song_b = _analysis(120.0, 200)

    result = suggest_transition_plan(song_a, song_b)

    assert result.song_a_gain_db == 0.0
    assert result.song_b_gain_db == 0.0


def test_missing_local_key_produces_neutral_harmonic_compatibility() -> None:
    # Candidates here never set local_key/local_mode (defaults to None).
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.harmonic_compatibility == 0.5


def test_crossfade_bias_defaults_to_zero() -> None:
    song_a = _analysis(120.0, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(120.0, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])

    result = suggest_transition_plan(song_a, song_b)

    assert result.crossfade_bias == 0.0
