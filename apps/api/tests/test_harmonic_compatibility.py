from itertools import pairwise

from app.services.harmonic_compatibility import (
    NEUTRAL_COMPATIBILITY,
    harmonic_compatibility,
)


def test_same_key_scores_highest() -> None:
    score = harmonic_compatibility("C", "major", "C", "major")
    assert score == 1.0


def test_relative_minor_scores_highly() -> None:
    # A minor is the relative minor of C major (same key signature).
    score = harmonic_compatibility("C", "major", "A", "minor")
    assert score >= 0.85
    assert score < 1.0


def test_relative_major_minor_is_symmetric() -> None:
    forward = harmonic_compatibility("C", "major", "A", "minor")
    backward = harmonic_compatibility("A", "minor", "C", "major")
    assert forward == backward


def test_parallel_major_minor_scores_moderately_high() -> None:
    # Same tonic, different mode (e.g. C major & C minor).
    score = harmonic_compatibility("C", "major", "C", "minor")
    assert 0.6 <= score < 0.9


def test_fifth_relationship_scores_appropriately() -> None:
    # G major is a perfect fifth above C major — closely related.
    fifth = harmonic_compatibility("C", "major", "G", "major")
    assert 0.7 <= fifth < 1.0


def test_fourth_relationship_scores_appropriately() -> None:
    # F major is a perfect fourth above C major (a fifth in the other
    # direction) — also closely related, and should score the same as the
    # fifth relationship by symmetry of the circle of fifths.
    fourth = harmonic_compatibility("C", "major", "F", "major")
    fifth = harmonic_compatibility("C", "major", "G", "major")
    assert fourth == fifth


def test_distant_key_relationship_scores_lower_than_closely_related() -> None:
    close = harmonic_compatibility("C", "major", "G", "major")
    distant = harmonic_compatibility("C", "major", "F#", "major")
    assert distant < close


def test_tritone_relationship_is_the_most_distant() -> None:
    """The tritone (6 steps on the circle of fifths) is the maximum
    possible distance and should score at or below every other distinct
    non-identical relationship tested here."""
    tritone = harmonic_compatibility("C", "major", "F#", "major")
    one_step = harmonic_compatibility("C", "major", "G", "major")
    two_step = harmonic_compatibility("C", "major", "D", "major")
    assert tritone <= two_step <= one_step


def test_compatibility_scores_are_monotonic_with_circle_of_fifths_distance() -> None:
    reference_scores = [
        harmonic_compatibility("C", "major", key, "major")
        for key in ("G", "D", "A", "E", "B", "F#")
    ]
    # Each step further around the circle of fifths should never score
    # *higher* than a closer one.
    for earlier, later in pairwise(reference_scores):
        assert later <= earlier


def test_cross_mode_fifth_scores_lower_than_same_mode_fifth() -> None:
    # G is a fifth above C either way, but C major -> G minor no longer
    # shares most of its pitch classes the way C major -> G major does.
    same_mode = harmonic_compatibility("C", "major", "G", "major")
    cross_mode = harmonic_compatibility("C", "major", "G", "minor")
    assert cross_mode < same_mode


def test_cross_mode_fifth_from_a_minor_scores_lower_than_same_mode_fifth() -> None:
    same_mode = harmonic_compatibility("A", "minor", "E", "minor")
    cross_mode = harmonic_compatibility("A", "minor", "E", "major")
    assert cross_mode < same_mode


def test_cross_mode_fifth_still_beats_a_distant_same_mode_relationship() -> None:
    # A cross-mode fifth/fourth is still a fairly close tonic relationship
    # — it should outrank two same-mode keys several steps apart.
    cross_mode_fifth = harmonic_compatibility("C", "major", "G", "minor")
    distant_same_mode = harmonic_compatibility("C", "major", "F#", "major")
    assert cross_mode_fifth > distant_same_mode


def test_cross_mode_fifth_does_not_reach_parallel_or_relative_scores() -> None:
    cross_mode_fifth = harmonic_compatibility("C", "major", "G", "minor")
    parallel = harmonic_compatibility("C", "major", "C", "minor")
    relative = harmonic_compatibility("C", "major", "A", "minor")
    assert cross_mode_fifth < parallel < relative


def test_missing_local_key_on_either_side_produces_neutral_compatibility() -> None:
    assert harmonic_compatibility(None, None, "C", "major") == NEUTRAL_COMPATIBILITY
    assert harmonic_compatibility("C", "major", None, None) == NEUTRAL_COMPATIBILITY
    assert harmonic_compatibility(None, None, None, None) == NEUTRAL_COMPATIBILITY


def test_missing_mode_alone_also_produces_neutral_compatibility() -> None:
    assert harmonic_compatibility("C", None, "C", "major") == NEUTRAL_COMPATIBILITY


def test_all_scores_are_within_the_documented_range() -> None:
    keys = ["C", "C#", "D", "F#", "A", "B"]
    modes = ["major", "minor"]
    for key_a in keys:
        for mode_a in modes:
            for key_b in keys:
                for mode_b in modes:
                    score = harmonic_compatibility(key_a, mode_a, key_b, mode_b)
                    assert 0.0 <= score <= 1.0
