"""Renders a short, beat-aligned crossfade preview between two tracks.

Song A keeps its native tempo; Song B is time-stretched (tempo only, pitch
unaffected) so its beat period matches Song A's. The two selected anchor
beats are aligned at the center of a fixed 16-beat window, and mixed with
an equal-power crossfade.

Performance note: this does NOT time-stretch or decode either track in
full. Only a small region of each track around its anchor is read from
disk (via soundfile's seek/read, falling back to a full decode only for
formats that aren't directly seekable), and only that region is stretched.
This keeps a multi-minute song from ever being fully loaded or stretched
for a preview that only needs a handful of seconds around one beat.
"""

import io
import math
from dataclasses import dataclass

import librosa
import numpy as np
import soundfile as sf

RENDER_SAMPLE_RATE = 44100

# Extra original-timeline audio read (and stretched) on each side of the
# region we actually keep, so the phase vocoder has real context at what
# would otherwise be a hard edge. Discarded after stretching.
STRETCH_MARGIN_SECONDS = 2.0


class TransitionRenderError(Exception):
    """Raised when a transition preview cannot be rendered from the given
    tracks/parameters. Callers should map this to a 4xx response."""


@dataclass
class RenderedTransition:
    wav_bytes: bytes
    sample_rate: int
    duration_seconds: float
    target_bpm: float


def render_transition(
    *,
    song_a_path: str,
    song_b_path: str,
    song_a_anchor_seconds: float,
    song_b_anchor_seconds: float,
    song_a_bpm: float,
    song_b_bpm: float,
    transition_beats: int = 16,
) -> RenderedTransition:
    _validate_bpm(song_a_bpm, "Song A")
    _validate_bpm(song_b_bpm, "Song B")
    _validate_anchor(song_a_anchor_seconds, "Song A")
    _validate_anchor(song_b_anchor_seconds, "Song B")

    target_bpm = song_a_bpm
    beat_period = 60.0 / target_bpm
    window_seconds = transition_beats * beat_period
    half_window = window_seconds / 2.0

    try:
        song_a_window = _render_song_a_window(
            song_a_path, song_a_anchor_seconds, half_window
        )
        song_b_window = _render_song_b_window(
            song_b_path,
            song_b_anchor_seconds,
            source_bpm=song_b_bpm,
            target_bpm=target_bpm,
            half_window=half_window,
        )
    except (
        RuntimeError,
        EOFError,
        ValueError,
    ) as exc:  # RuntimeError covers sf.LibsndfileError
        raise TransitionRenderError("Could not decode one of the tracks.") from exc

    n_samples = round(window_seconds * RENDER_SAMPLE_RATE)
    channels = max(song_a_window.shape[1], song_b_window.shape[1])
    song_a_window = _match_length(_to_channels(song_a_window, channels), n_samples)
    song_b_window = _match_length(_to_channels(song_b_window, channels), n_samples)

    mixed = _equal_power_mix(song_a_window, song_b_window)
    mixed = _safety_limit(mixed)

    buffer_bytes = _write_wav(mixed, RENDER_SAMPLE_RATE)

    return RenderedTransition(
        wav_bytes=buffer_bytes,
        sample_rate=RENDER_SAMPLE_RATE,
        duration_seconds=n_samples / RENDER_SAMPLE_RATE,
        target_bpm=target_bpm,
    )


def _validate_bpm(bpm: float, label: str) -> None:
    if not math.isfinite(bpm) or bpm <= 0:
        raise TransitionRenderError(f"{label} has an invalid BPM ({bpm!r}).")


def _validate_anchor(seconds: float, label: str) -> None:
    if not math.isfinite(seconds) or seconds < 0:
        raise TransitionRenderError(
            f"{label} has an invalid anchor time ({seconds!r})."
        )


def _render_song_a_window(
    path: str, anchor_seconds: float, half_window: float
) -> np.ndarray:
    """Song A is not tempo-shifted, so its window is a direct (padded) slice
    of the source audio around the anchor."""
    start = anchor_seconds - half_window
    end = anchor_seconds + half_window

    y, native_sr, actual_start = _read_window(path, start, end)
    y = _resample_if_needed(y, native_sr, RENDER_SAMPLE_RATE)

    relative_start = start - actual_start
    relative_end = relative_start + (end - start)
    return _extract_with_padding(y, RENDER_SAMPLE_RATE, relative_start, relative_end)


def _render_song_b_window(
    path: str,
    anchor_seconds: float,
    *,
    source_bpm: float,
    target_bpm: float,
    half_window: float,
) -> np.ndarray:
    """Song B is time-stretched so its beat period matches Song A's, then
    its window is extracted from the *stretched* timeline so the anchors
    end up aligned in the final mix."""
    stretch_rate = target_bpm / source_bpm  # >1 speeds up, <1 slows down

    stretched_anchor = anchor_seconds / stretch_rate
    stretched_window_start = stretched_anchor - half_window
    stretched_window_end = stretched_anchor + half_window

    # Map the stretched-timeline window (plus margin) back to Song B's
    # original timeline to know what to read from disk.
    original_read_start = max(
        0.0, (stretched_window_start - STRETCH_MARGIN_SECONDS) * stretch_rate
    )
    original_read_end = (stretched_window_end + STRETCH_MARGIN_SECONDS) * stretch_rate

    y, native_sr, actual_read_start = _read_window(
        path, original_read_start, original_read_end
    )
    y = _resample_if_needed(y, native_sr, RENDER_SAMPLE_RATE)

    if y.shape[0] == 0:
        stretched = np.zeros((0, 1), dtype=np.float32)
    else:
        stretched = _time_stretch_channels_last(y, stretch_rate)

    # This slice of the *original* track started at `actual_read_start`;
    # under the same uniform linear stretch, that maps to this position on
    # the stretched timeline.
    stretched_slice_start = actual_read_start / stretch_rate

    relative_start = stretched_window_start - stretched_slice_start
    relative_end = relative_start + (stretched_window_end - stretched_window_start)
    return _extract_with_padding(
        stretched, RENDER_SAMPLE_RATE, relative_start, relative_end
    )


def _read_window(
    path: str, start_seconds: float, end_seconds: float
) -> tuple[np.ndarray, int, float]:
    """Reads only [start_seconds, end_seconds) (clamped to the file's actual
    bounds) directly from disk where the format is seekable. Returns
    (samples shape (n, channels) float32, native sample rate, the actual
    start time of the returned samples — which can differ from the request
    when clamped at the start of the file).

    Falls back to decoding the whole file via librosa for formats that
    aren't directly seekable through libsndfile (e.g. some AAC streams);
    slower, but still correct.
    """
    try:
        with sf.SoundFile(path) as f:
            native_sr = f.samplerate
            total_frames = len(f)
            start_frame = _clamp_frame(start_seconds, native_sr, total_frames)
            end_frame = max(
                start_frame, _clamp_frame(end_seconds, native_sr, total_frames)
            )
            f.seek(start_frame)
            data = f.read(
                frames=end_frame - start_frame, dtype="float32", always_2d=True
            )
        return data, native_sr, start_frame / native_sr
    except RuntimeError:  # covers sf.LibsndfileError, which subclasses it
        y, native_sr = librosa.load(path, sr=None, mono=False)
        y = np.atleast_2d(y).T  # -> (n, channels), covers mono (n,) too
        total_frames = y.shape[0]
        start_frame = _clamp_frame(start_seconds, native_sr, total_frames)
        end_frame = max(start_frame, _clamp_frame(end_seconds, native_sr, total_frames))
        return y[start_frame:end_frame], native_sr, start_frame / native_sr


def _clamp_frame(seconds: float, sr: float, total_frames: int) -> int:
    frame = round(seconds * sr)
    return min(max(frame, 0), total_frames)


def _resample_if_needed(y: np.ndarray, native_sr: int, target_sr: int) -> np.ndarray:
    if native_sr == target_sr or y.shape[0] == 0:
        return y
    return librosa.resample(y, orig_sr=native_sr, target_sr=target_sr, axis=0)


def _time_stretch_channels_last(y: np.ndarray, rate: float) -> np.ndarray:
    """`librosa.effects.time_stretch` requires time as the *last* axis;
    our internal convention is channels-last (n, channels), so transpose
    there and back."""
    stretched = librosa.effects.time_stretch(np.ascontiguousarray(y.T), rate=rate)
    return np.ascontiguousarray(stretched.T)


def _extract_with_padding(
    y: np.ndarray, sr: int, start_seconds: float, end_seconds: float
) -> np.ndarray:
    """Returns exactly the [start_seconds, end_seconds) window at `sr`,
    zero-padding any portion that falls outside `y`'s actual range."""
    total = y.shape[0]
    channels = y.shape[1] if y.ndim == 2 and y.shape[1] > 0 else 1
    y2 = (
        y.reshape(total, channels) if y.size else np.zeros((0, channels), dtype=y.dtype)
    )

    start_sample = round(start_seconds * sr)
    end_sample = round(end_seconds * sr)
    length = max(0, end_sample - start_sample)

    out = np.zeros((length, channels), dtype=np.float32)

    src_start = max(start_sample, 0)
    src_end = min(end_sample, total)
    if src_start < src_end:
        dst_start = src_start - start_sample
        dst_end = dst_start + (src_end - src_start)
        out[dst_start:dst_end] = y2[src_start:src_end]

    return out


def _to_channels(y: np.ndarray, target_channels: int) -> np.ndarray:
    channels = y.shape[1]
    if channels == target_channels:
        return y
    if channels == 1 and target_channels > 1:
        return np.repeat(y, target_channels, axis=1)
    if channels > 1 and target_channels == 1:
        return y.mean(axis=1, keepdims=True).astype(y.dtype)
    if channels > target_channels:
        return y[:, :target_channels]
    pad = np.repeat(y[:, -1:], target_channels - channels, axis=1)
    return np.concatenate([y, pad], axis=1)


def _match_length(y: np.ndarray, n_samples: int) -> np.ndarray:
    current = y.shape[0]
    if current == n_samples:
        return y
    if current > n_samples:
        return y[:n_samples]
    pad = np.zeros((n_samples - current, y.shape[1]), dtype=y.dtype)
    return np.concatenate([y, pad], axis=0)


def _equal_power_mix(song_a: np.ndarray, song_b: np.ndarray) -> np.ndarray:
    n = song_a.shape[0]
    x = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float64)
    gain_a = np.cos(x * np.pi / 2.0).astype(np.float32)
    gain_b = np.sin(x * np.pi / 2.0).astype(np.float32)
    return song_a * gain_a[:, None] + song_b * gain_b[:, None]


def _safety_limit(mixed: np.ndarray) -> np.ndarray:
    """Crossfaded regions can still sum above unity; scale down uniformly
    (never adds distortion/compression, just headroom) rather than clip."""
    mixed = np.nan_to_num(mixed, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 1.0:
        mixed = mixed / peak
    return mixed


def _write_wav(mixed: np.ndarray, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, mixed, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()
