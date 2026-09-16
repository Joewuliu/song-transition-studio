"""Deterministic music-theory comparison between two local harmonic
contexts (an estimated key + mode, each with its own confidence).

This does not claim to predict subjective musical quality — it only
scores how closely related two (key, mode) pairs are using well-known,
documented relationships (same key, relative major/minor, fifth/fourth,
parallel major/minor, and circle-of-fifths distance for everything else).
"""

# 0.0 = strongly incompatible/unrelated, 1.0 = highly compatible. Used
# whenever either side's harmonic context is missing/unreliable, since a
# genuinely unknown relationship should read as neutral, not as a penalty.
NEUTRAL_COMPATIBILITY = 0.5

PITCH_CLASS_TO_SEMITONE: dict[str, int] = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}

# Position of each pitch class on the circle of fifths (C=0, then +1 for
# each perfect fifth: C, G, D, A, E, B, F#, C#, G#, D#, A#, F).
SEMITONE_TO_FIFTHS_POSITION: dict[int, int] = {
    0: 0,
    7: 1,
    2: 2,
    9: 3,
    4: 4,
    11: 5,
    6: 6,
    1: 7,
    8: 8,
    3: 9,
    10: 10,
    5: 11,
}

# Compatibility by circle-of-fifths distance between the two keys' shared
# "relative major" reference (see _relative_major_semitone), for pairs that
# are neither identical nor a relative/parallel major-minor pair. Distance
# 0 never reaches this table (it's the identical/relative case above);
# distance 6 (a tritone apart) is the most harmonically distant pair.
FIFTHS_DISTANCE_COMPATIBILITY: dict[int, float] = {
    1: 0.8,
    2: 0.55,
    3: 0.35,
    4: 0.27,
    5: 0.19,
    6: 0.11,
}

COMPATIBLE_SAME_KEY = 1.0
COMPATIBLE_RELATIVE_MAJOR_MINOR = 0.9
COMPATIBLE_PARALLEL_MAJOR_MINOR = 0.75

# Applied to the same-mode fifths-distance score whenever the two tonics
# are a given circle-of-fifths distance apart but the modes differ (and
# the pair isn't already one of the explicit relationships above). A fifth
# apart in the SAME mode (e.g. C major -> G major) is a well-known, very
# closely related pair; the same tonic distance across DIFFERENT modes
# (e.g. C major -> G minor) is related but distinctly less so, since the
# two keys no longer share most of their pitch classes. Chosen so a
# cross-mode fifth still clearly outranks a distant same-mode relationship
# without approaching the explicit parallel/relative scores above.
CROSS_MODE_FIFTH_PENALTY = 0.7


def harmonic_compatibility(
    key_a: str | None,
    mode_a: str | None,
    key_b: str | None,
    mode_b: str | None,
) -> float:
    """Scores how harmonically compatible two local (key, mode) contexts
    are, in [0, 1]. Returns NEUTRAL_COMPATIBILITY if either side is
    unknown (None) rather than guessing or penalizing missing data."""
    if key_a is None or mode_a is None or key_b is None or mode_b is None:
        return NEUTRAL_COMPATIBILITY

    semitone_a = PITCH_CLASS_TO_SEMITONE.get(key_a)
    semitone_b = PITCH_CLASS_TO_SEMITONE.get(key_b)
    if semitone_a is None or semitone_b is None:
        return NEUTRAL_COMPATIBILITY

    if semitone_a == semitone_b and mode_a == mode_b:
        return COMPATIBLE_SAME_KEY

    relative_major_a = _relative_major_semitone(semitone_a, mode_a)
    relative_major_b = _relative_major_semitone(semitone_b, mode_b)

    if relative_major_a == relative_major_b:
        # Same key signature, different tonic/mode: relative major/minor
        # (e.g. C major & A minor share every pitch class).
        return COMPATIBLE_RELATIVE_MAJOR_MINOR

    if semitone_a == semitone_b and mode_a != mode_b:
        # Same tonic, different mode: parallel major/minor (e.g. C major &
        # C minor) — a common, smooth "modal interchange" relationship.
        return COMPATIBLE_PARALLEL_MAJOR_MINOR

    # Everything else: distance between the two TONICS on the circle of
    # fifths (not the relative-major-shifted distance above) — this is
    # the plain, well-known "how many fifths apart are these two keys"
    # question, independent of mode. Note that when mode_a == mode_b this
    # is mathematically identical to the relative-major distance (an equal
    # +3-semitone shift to both minor tonics leaves their circular
    # distance unchanged), so same-mode fifth/fourth scores are unaffected
    # by this restructuring.
    distance = _circle_of_fifths_distance(semitone_a, semitone_b)
    same_mode_score = FIFTHS_DISTANCE_COMPATIBILITY.get(distance, NEUTRAL_COMPATIBILITY)

    if mode_a == mode_b:
        return same_mode_score
    return round(same_mode_score * CROSS_MODE_FIFTH_PENALTY, 6)


def _relative_major_semitone(semitone: int, mode: str) -> int:
    """The semitone of the major key sharing this key's pitch classes/key
    signature. For a major key that's itself; for a minor key it's a minor
    third (3 semitones) above the minor tonic (e.g. A minor -> C major)."""
    if mode == "major":
        return semitone
    return (semitone + 3) % 12


def _circle_of_fifths_distance(semitone_a: int, semitone_b: int) -> int:
    """Shortest distance (0-6) between two pitch classes on the circle of
    fifths — musically closely related keys differ by a small number of
    fifths, not a small number of chromatic semitones."""
    position_a = SEMITONE_TO_FIFTHS_POSITION[semitone_a]
    position_b = SEMITONE_TO_FIFTHS_POSITION[semitone_b]
    raw_distance = abs(position_a - position_b)
    return min(raw_distance, 12 - raw_distance)
