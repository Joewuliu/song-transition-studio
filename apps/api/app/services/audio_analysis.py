"""Musical analysis (tempo/beats) for uploaded audio, backed by librosa.

Uploaded audio is never kept: each call writes the given bytes to a private
temporary file (librosa/soundfile need a real path for some codecs), decodes
it, and removes the file again before returning.
"""

import os
import tempfile
from pathlib import Path

import librosa
import numpy as np

from app.schemas import TrackAnalysis


class AudioAnalysisError(Exception):
    """Raised when uploaded audio cannot be decoded or analyzed."""


def analyze_audio(data: bytes, filename_hint: str = "") -> TrackAnalysis:
    """Decode `data` as audio and return its duration, tempo, and beats.

    `filename_hint` is only used to preserve a file suffix for the decoder;
    it is never used as a storage path.
    """
    suffix = Path(filename_hint).suffix

    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)

        # The file handle above is fully closed before librosa opens the
        # path, which avoids sharing-violation errors on Windows.
        y, sr = _decode_mono(tmp_path)
        return _analyze_signal(y, sr)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            # Already gone, or a decoder still had it briefly open; either
            # way there is nothing further we can safely do here.
            pass


def _decode_mono(path: str) -> tuple[np.ndarray, float]:
    try:
        y, sr = librosa.load(path, sr=None, mono=True)
    except Exception as exc:
        raise AudioAnalysisError("Could not decode audio file.") from exc

    if y.size == 0:
        raise AudioAnalysisError("Audio file contains no audio data.")

    return y, sr


def _analyze_signal(y: np.ndarray, sr: float) -> TrackAnalysis:
    duration_seconds = float(librosa.get_duration(y=y, sr=sr))
    tempo_bpm, beats = _detect_tempo_and_beats(y, sr)

    return TrackAnalysis(
        duration_seconds=round(duration_seconds, 3),
        tempo_bpm=round(tempo_bpm, 2),
        beat_count=len(beats),
        beats=beats,
    )


def _detect_tempo_and_beats(y: np.ndarray, sr: float) -> tuple[float, list[float]]:
    """Best-effort tempo/beat detection.

    Confident detection is not guaranteed for every input (silence, noise,
    very short clips, ...); any failure here degrades to "no tempo/beats
    detected" rather than propagating an error, since the audio itself
    decoded successfully.
    """
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    except (
        librosa.LibrosaError,
        ValueError,
        IndexError,
        RuntimeError,
        np.linalg.LinAlgError,
    ):
        return 0.0, []

    tempo_bpm = _as_scalar_tempo(tempo)

    if beat_frames.size == 0:
        return tempo_bpm, []

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beats = sorted(float(t) for t in beat_times if np.isfinite(t))
    beats = [round(t, 3) for t in beats]

    return tempo_bpm, beats


def _as_scalar_tempo(tempo: float | np.floating | np.integer | np.ndarray) -> float:
    """Normalize librosa's tempo return value to a plain, finite float.

    Depending on librosa version and inputs, `beat_track` may return tempo
    as a Python float, a NumPy scalar, or a 1-element (or empty) ndarray.
    """
    values = np.atleast_1d(np.asarray(tempo, dtype=float))
    if values.size == 0 or not np.isfinite(values[0]):
        return 0.0
    return float(values[0])
