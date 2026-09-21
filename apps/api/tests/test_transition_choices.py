"""M12: pairwise candidate-pair search — the scoring formula's individual
terms, diversity filtering, and the end-to-end suggest_transition_choices
entry point. See services/transition_planner.py's module docstring for the
formula this exercises."""

from app.schemas import TrackAnalysis, TransitionCandidate
from app.services.transition_planner import (
    DIVERSITY_MIN_BEAT_GAP,
    MAX_CHOICES,
    _energy_continuity_score,
    _is_distinct_pair,
    _rhythmic_compatibility_score,
    _score_pair,
    _select_diverse_pairs,
    _tempo_compatibility_term,
    _timbral_compatibility_score,
    suggest_transition_choices,
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
    score: float = 0.5,
    *,
    energy_before: float = 0.1,
    energy_after: float = 0.1,
    boundary_strength: float = 0.5,
    local_key: str | None = None,
    local_mode: str | None = None,
    local_timbre: list[float] | None = None,
) -> TransitionCandidate:
    return TransitionCandidate(
        beat_index=beat_index,
        time_seconds=time_seconds,
        score=score,
        boundary_strength=boundary_strength,
        energy_before=energy_before,
        energy_after=energy_after,
        local_key=local_key,
        local_mode=local_mode,
        local_timbre=local_timbre,
    )


# ---------------------------------------------------------------------------
# Individual scoring terms
# ---------------------------------------------------------------------------


def test_tempo_term_is_perfect_at_zero_change_magnitude() -> None:
    assert _tempo_compatibility_term(0.0) == 1.0


def test_tempo_term_prefers_compatible_over_severe_mismatch() -> None:
    compatible = _tempo_compatibility_term(0.01)
    severe = _tempo_compatibility_term(0.30)
    assert compatible > severe
    assert severe == 0.0


def test_tempo_term_stays_within_bounds_past_the_zero_point() -> None:
    assert _tempo_compatibility_term(10.0) == 0.0


def test_energy_continuity_is_perfect_for_matched_levels() -> None:
    matched_exit = _candidate(1, 1.0, energy_before=0.2, energy_after=0.2)
    matched_entry = _candidate(2, 2.0, energy_before=0.2, energy_after=0.2)
    assert _energy_continuity_score(matched_exit, matched_entry) == 1.0


def test_extreme_energy_discontinuity_is_penalized() -> None:
    loud_exit = _candidate(1, 1.0, energy_before=0.9, energy_after=0.9)
    silent_entry = _candidate(2, 2.0, energy_before=1e-5, energy_after=1e-5)
    matched_entry = _candidate(3, 3.0, energy_before=0.9, energy_after=0.9)

    discontinuous = _energy_continuity_score(loud_exit, silent_entry)
    continuous = _energy_continuity_score(loud_exit, matched_entry)

    assert discontinuous < continuous
    assert discontinuous < 0.5


def test_energy_continuity_absorbs_small_gaps_within_the_gain_trim_limit() -> None:
    # A ~3 dB gap is well within GAIN_MATCH_LIMIT_DB (6 dB) — the existing
    # gain suggestion can fully compensate, so this should score perfectly.
    exit_candidate = _candidate(1, 1.0, energy_before=0.2, energy_after=0.2)
    entry_candidate = _candidate(2, 2.0, energy_before=0.14, energy_after=0.14)
    assert _energy_continuity_score(exit_candidate, entry_candidate) == 1.0


def test_timbral_compatibility_is_perfect_for_identical_vectors() -> None:
    vector = [0.1, 0.2, -0.3, 0.4, 0.0, 0.5, -0.1, 0.2, 0.3, -0.2, 0.1, 0.0, 0.4]
    exit_candidate = _candidate(1, 1.0, local_timbre=vector)
    entry_candidate = _candidate(2, 2.0, local_timbre=list(vector))
    assert _timbral_compatibility_score(exit_candidate, entry_candidate) == 1.0


def test_timbral_compatibility_is_lower_for_opposite_vectors() -> None:
    vector = [0.1, 0.2, -0.3, 0.4, 0.0, 0.5, -0.1, 0.2, 0.3, -0.2, 0.1, 0.0, 0.4]
    opposite = [-value for value in vector]
    exit_candidate = _candidate(1, 1.0, local_timbre=vector)
    entry_candidate = _candidate(2, 2.0, local_timbre=opposite)
    assert _timbral_compatibility_score(exit_candidate, entry_candidate) == 0.0


def test_timbral_compatibility_is_neutral_without_timbre_data() -> None:
    exit_candidate = _candidate(1, 1.0, local_timbre=None)
    entry_candidate = _candidate(2, 2.0, local_timbre=[0.1] * 13)
    assert _timbral_compatibility_score(exit_candidate, entry_candidate) == 0.5


def test_rhythmic_compatibility_is_perfect_for_equal_boundary_strength() -> None:
    exit_candidate = _candidate(1, 1.0, boundary_strength=0.4)
    entry_candidate = _candidate(2, 2.0, boundary_strength=0.4)
    assert _rhythmic_compatibility_score(exit_candidate, entry_candidate) == 1.0


def test_rhythmic_compatibility_drops_for_lopsided_onset_density() -> None:
    busy_exit = _candidate(1, 1.0, boundary_strength=2.0)
    sparse_entry = _candidate(2, 2.0, boundary_strength=0.01)
    assert _rhythmic_compatibility_score(busy_exit, sparse_entry) < 0.5


def test_missing_key_info_does_not_break_scoring() -> None:
    exit_candidate = _candidate(1, 1.0, local_key=None, local_mode=None)
    entry_candidate = _candidate(2, 2.0, local_key=None, local_mode=None)
    pair = _score_pair(exit_candidate, entry_candidate, tempo_term=1.0)
    assert pair.harmonic_compatibility == 0.5
    assert 0.0 <= pair.score <= 1.0


def test_strong_candidate_quality_is_rewarded() -> None:
    """Holding harmony/energy/timbre/rhythm fixed, a higher exit/entry
    candidate score (structural + boundary + energy + position — see
    audio_analysis.py) must produce a higher pair score."""
    weak_exit = _candidate(1, 1.0, score=0.1)
    strong_exit = _candidate(2, 2.0, score=0.95)
    entry = _candidate(3, 3.0, score=0.5)

    weak_pair = _score_pair(weak_exit, entry, tempo_term=0.5)
    strong_pair = _score_pair(strong_exit, entry, tempo_term=0.5)

    assert strong_pair.score > weak_pair.score


def test_pair_score_is_always_bounded_0_to_1() -> None:
    best_case = _candidate(
        1,
        1.0,
        score=1.0,
        boundary_strength=1.0,
        energy_before=0.5,
        energy_after=0.5,
        local_key="C",
        local_mode="major",
        local_timbre=[1.0] * 13,
    )
    best_entry = _candidate(
        2,
        2.0,
        score=1.0,
        boundary_strength=1.0,
        energy_before=0.5,
        energy_after=0.5,
        local_key="C",
        local_mode="major",
        local_timbre=[1.0] * 13,
    )
    worst_case = _candidate(
        3,
        3.0,
        score=0.0,
        boundary_strength=0.0,
        energy_before=1e-6,
        energy_after=1e-6,
        local_key="F#",
        local_mode="major",
        local_timbre=[-1.0] * 13,
    )
    worst_entry = _candidate(
        4,
        4.0,
        score=0.0,
        boundary_strength=100.0,
        energy_before=0.99,
        energy_after=0.99,
        local_key="C",
        local_mode="major",
        local_timbre=[1.0] * 13,
    )

    best = _score_pair(best_case, best_entry, tempo_term=1.0)
    worst = _score_pair(worst_case, worst_entry, tempo_term=0.0)

    assert 0.0 <= best.score <= 1.0
    assert 0.0 <= worst.score <= 1.0
    assert best.score > worst.score


# ---------------------------------------------------------------------------
# Diversity filtering
# ---------------------------------------------------------------------------


def test_is_distinct_pair_true_when_either_side_differs_enough() -> None:
    a_exit = _candidate(10, 5.0)
    a_entry = _candidate(20, 10.0)
    b_exit = _candidate(10 + DIVERSITY_MIN_BEAT_GAP, 5.5)
    b_entry = _candidate(20, 10.0)

    pair_a = _score_pair(a_exit, a_entry, tempo_term=1.0)
    pair_b = _score_pair(b_exit, b_entry, tempo_term=1.0)

    assert _is_distinct_pair(pair_a, pair_b) is True


def test_is_distinct_pair_false_when_both_sides_are_neighboring_beats() -> None:
    a_exit = _candidate(10, 5.0)
    a_entry = _candidate(20, 10.0)
    b_exit = _candidate(11, 5.1)  # one beat away
    b_entry = _candidate(21, 10.1)  # one beat away

    pair_a = _score_pair(a_exit, a_entry, tempo_term=1.0)
    pair_b = _score_pair(b_exit, b_entry, tempo_term=1.0)

    assert _is_distinct_pair(pair_a, pair_b) is False


def test_diversity_filtering_prevents_adjacent_duplicate_choices() -> None:
    # Three near-identical, adjacent-beat candidates on each side (all
    # scoring almost the same) plus one genuinely distant, distinct pair.
    exits = [_candidate(100 + i, 50.0 + i, score=0.9) for i in range(3)]
    entries = [_candidate(10 + i, 5.0 + i, score=0.9) for i in range(3)]
    distinct_exit = _candidate(5, 2.5, score=0.85)
    distinct_entry = _candidate(150, 75.0, score=0.85)

    scored = [
        _score_pair(exit_c, entry_c, tempo_term=1.0)
        for exit_c in [*exits, distinct_exit]
        for entry_c in [*entries, distinct_entry]
    ]
    scored.sort(key=lambda pair: pair.score, reverse=True)

    selected = _select_diverse_pairs(scored, target=2)

    assert len(selected) == 2
    assert _is_distinct_pair(selected[0], selected[1])


def test_diversity_filtering_backfills_when_too_few_distinct_pairs_exist() -> None:
    # Only two candidates on each side, both pairs mutually near-duplicate
    # (adjacent beats both sides) — fewer than MAX_CHOICES genuinely
    # distinct pairs exist, so the selector must still return up to the
    # number of pairs that actually exist rather than fewer.
    exits = [_candidate(10, 5.0, score=0.9), _candidate(11, 5.1, score=0.8)]
    entries = [_candidate(20, 10.0, score=0.9), _candidate(21, 10.1, score=0.8)]
    scored = [
        _score_pair(exit_c, entry_c, tempo_term=1.0)
        for exit_c in exits
        for entry_c in entries
    ]
    scored.sort(key=lambda pair: pair.score, reverse=True)

    # target exceeds the total number of pairs that exist at all, so the
    # backfill must return every pair rather than stopping at whatever
    # diversity alone would have selected.
    selected = _select_diverse_pairs(scored, target=len(scored) + 2)

    assert len(selected) == len(scored)


# ---------------------------------------------------------------------------
# End-to-end: suggest_transition_choices
# ---------------------------------------------------------------------------


def _wide_candidate_pools() -> tuple[TrackAnalysis, TrackAnalysis]:
    """Enough spread-out, varied candidates on each side that a real
    pairwise search (not just the fallback path) runs, and that at least
    MAX_CHOICES genuinely distinct pairs exist."""
    exits = [
        _candidate(
            60 + i * 6,
            30.0 + i * 3.0,
            score=0.5 + 0.05 * i,
            local_key=["C", "G", "D", "A"][i % 4],
            local_mode="major",
        )
        for i in range(8)
    ]
    entries = [
        _candidate(
            5 + i * 5,
            2.5 + i * 2.5,
            score=0.5 + 0.04 * i,
            local_key=["C", "G", "D", "A"][i % 4],
            local_mode="major",
        )
        for i in range(8)
    ]
    song_a = _analysis(120.0, 300, exit_candidates=exits)
    song_b = _analysis(120.0, 300, entry_candidates=entries)
    return song_a, song_b


def test_returns_up_to_max_choices_when_pool_is_wide_enough() -> None:
    song_a, song_b = _wide_candidate_pools()
    result = suggest_transition_choices(song_a, song_b)
    assert len(result.choices) == MAX_CHOICES


def test_choices_are_ranked_best_first() -> None:
    song_a, song_b = _wide_candidate_pools()
    result = suggest_transition_choices(song_a, song_b)
    scores = [choice.compatibility for choice in result.choices]
    assert scores == sorted(scores, reverse=True)


def test_choices_are_deterministic_across_repeated_calls() -> None:
    song_a, song_b = _wide_candidate_pools()
    first = suggest_transition_choices(song_a, song_b)
    second = suggest_transition_choices(song_a, song_b)
    assert first == second


def test_choices_are_mutually_distinct() -> None:
    song_a, song_b = _wide_candidate_pools()
    result = suggest_transition_choices(song_a, song_b)

    for i, choice_a in enumerate(result.choices):
        for choice_b in result.choices[i + 1 :]:
            a_gap = abs(
                choice_a.song_a_anchor.beat_index - choice_b.song_a_anchor.beat_index
            )
            b_gap = abs(
                choice_a.song_b_anchor.beat_index - choice_b.song_b_anchor.beat_index
            )
            assert a_gap >= DIVERSITY_MIN_BEAT_GAP or b_gap >= DIVERSITY_MIN_BEAT_GAP


def test_choice_plans_use_exactly_the_anchors_that_were_scored() -> None:
    song_a, song_b = _wide_candidate_pools()
    result = suggest_transition_choices(song_a, song_b)

    exit_by_beat = {c.beat_index: c for c in song_a.exit_candidates}
    entry_by_beat = {c.beat_index: c for c in song_b.entry_candidates}

    for choice in result.choices:
        assert choice.song_a_anchor.beat_index in exit_by_beat
        assert choice.song_b_anchor.beat_index in entry_by_beat
        assert (
            choice.song_a_anchor.time_seconds
            == exit_by_beat[choice.song_a_anchor.beat_index].time_seconds
        )
        assert (
            choice.song_b_anchor.time_seconds
            == entry_by_beat[choice.song_b_anchor.beat_index].time_seconds
        )


def test_choice_ids_and_labels_are_stable_rank_based() -> None:
    song_a, song_b = _wide_candidate_pools()
    result = suggest_transition_choices(song_a, song_b)

    assert [choice.id for choice in result.choices] == ["1", "2", "3"]
    assert result.choices[0].label == "Suggested transition"
