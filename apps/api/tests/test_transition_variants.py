from app.schemas import TrackAnalysis, TransitionCandidate, TransitionRenderRequest
from app.services.transition_planner import (
    QUICK_MIX_LENGTH_BY_BASE_LENGTH,
    TransitionSuggestionResult,
    build_transition_variants,
    suggest_transition_plan,
)
from app.services.transition_renderer import _valid_bass_swap_range


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
    beat_index: int, time_seconds: float, score: float
) -> TransitionCandidate:
    return TransitionCandidate(
        beat_index=beat_index,
        time_seconds=time_seconds,
        score=score,
        boundary_strength=0.5,
        energy_before=0.1,
        energy_after=0.2,
    )


def _result(song_a_bpm: float, song_b_bpm: float) -> TransitionSuggestionResult:
    song_a = _analysis(song_a_bpm, 200, exit_candidates=[_candidate(150, 75.0, 1.0)])
    song_b = _analysis(song_b_bpm, 200, entry_candidates=[_candidate(10, 5.0, 1.0)])
    return suggest_transition_plan(song_a, song_b)


# BPM pairs chosen (see _choose_length_and_compatibility's thresholds) so
# the base suggestion lands on each of the three supported transition
# lengths, to exercise the bass-swap-width and quick-mix-length policies
# at every base length.
BASE_32 = _result(128.0, 128.0)  # magnitude 0 -> 32, "compatible"
BASE_16 = _result(128.0, 120.0)  # magnitude ~0.065 -> 16, "moderate"
BASE_8 = _result(128.0, 100.0)  # magnitude ~0.247 -> 8, "significant"


def test_exactly_the_expected_variant_ids_are_produced() -> None:
    variants = build_transition_variants(BASE_32)
    assert [variant.id for variant in variants] == ["smooth", "bass_swap", "quick"]


def test_variant_generation_is_deterministic() -> None:
    first = build_transition_variants(BASE_16)
    second = build_transition_variants(BASE_16)
    assert first == second


def test_all_variants_preserve_the_base_anchors() -> None:
    for variant in build_transition_variants(BASE_16):
        assert variant.plan.song_a_anchor == BASE_16.song_a_anchor
        assert variant.plan.song_b_anchor == BASE_16.song_b_anchor


def test_all_variants_preserve_song_b_tempo_multiplier() -> None:
    for variant in build_transition_variants(BASE_16):
        assert variant.plan.song_b_tempo_multiplier == BASE_16.song_b_tempo_multiplier


def test_smooth_variant_has_smooth_transition_style() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_32)}
    assert variants["smooth"].plan.transition_style == "smooth"


def test_bass_swap_variant_has_bass_swap_transition_style() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_32)}
    assert variants["bass_swap"].plan.transition_style == "bass_swap"


def test_bass_swap_produces_a_valid_width_for_an_8_beat_base() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_8)}
    assert variants["bass_swap"].plan.transition_beats == 8
    assert variants["bass_swap"].plan.bass_swap_width_beats == 2


def test_bass_swap_produces_a_valid_width_for_a_16_beat_base() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_16)}
    assert variants["bass_swap"].plan.transition_beats == 16
    assert variants["bass_swap"].plan.bass_swap_width_beats == 4


def test_bass_swap_produces_a_valid_width_for_a_32_beat_base() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_32)}
    assert variants["bass_swap"].plan.transition_beats == 32
    assert variants["bass_swap"].plan.bass_swap_width_beats == 8


def test_bass_swap_position_remains_valid_at_every_base_length() -> None:
    for base in (BASE_8, BASE_16, BASE_32):
        variants = {v.id: v for v in build_transition_variants(base)}
        bass_swap = variants["bass_swap"].plan
        low, high = _valid_bass_swap_range(
            bass_swap.transition_beats, bass_swap.bass_swap_width_beats
        )
        assert low <= bass_swap.bass_swap_position <= high


def test_quick_mix_maps_32_to_16() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_32)}
    assert variants["quick"].plan.transition_beats == 16


def test_quick_mix_maps_16_to_8() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_16)}
    assert variants["quick"].plan.transition_beats == 8


def test_quick_mix_maps_8_to_8() -> None:
    variants = {v.id: v for v in build_transition_variants(BASE_8)}
    assert variants["quick"].plan.transition_beats == 8


def test_quick_mix_length_policy_covers_every_supported_base_length() -> None:
    assert QUICK_MIX_LENGTH_BY_BASE_LENGTH == {32: 16, 16: 8, 8: 8}


def test_no_variant_violates_backend_render_validation() -> None:
    for base in (BASE_8, BASE_16, BASE_32):
        for variant in build_transition_variants(base):
            plan = variant.plan
            # Raises pydantic.ValidationError on any invalid combination
            # (including the bass-swap-window cross-field check) — a plain
            # construction succeeding is the assertion.
            TransitionRenderRequest(
                song_a_anchor={
                    "beat_index": plan.song_a_anchor.beat_index,
                    "time_seconds": plan.song_a_anchor.time_seconds,
                },
                song_b_anchor={
                    "beat_index": plan.song_b_anchor.beat_index,
                    "time_seconds": plan.song_b_anchor.time_seconds,
                },
                song_a_bpm=128.0,
                song_b_bpm=120.0,
                transition_beats=plan.transition_beats,
                song_a_gain_db=plan.song_a_gain_db,
                song_b_gain_db=plan.song_b_gain_db,
                crossfade_bias=plan.crossfade_bias,
                song_b_tempo_multiplier=plan.song_b_tempo_multiplier,
                transition_style=plan.transition_style,
                bass_swap_position=plan.bass_swap_position,
                bass_swap_width_beats=plan.bass_swap_width_beats,
            )
