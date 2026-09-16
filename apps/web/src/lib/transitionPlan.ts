/**
 * A transition anchor identifies a specific detected beat on a track, not
 * an arbitrary waveform position. `beatIndex` is the zero-based index into
 * that track's analyzed `beats` array; `timeSeconds` is copied verbatim
 * from that array entry (never a rounded/visual approximation).
 */
export interface BeatAnchor {
  beatIndex: number;
  timeSeconds: number;
}

export type TransitionBeats = 8 | 16 | 32;

export const TRANSITION_BEATS_OPTIONS: readonly TransitionBeats[] = [8, 16, 32];

export const GAIN_DB_MIN = -12;
export const GAIN_DB_MAX = 6;
export const CROSSFADE_BIAS_MIN = -1;
export const CROSSFADE_BIAS_MAX = 1;

export const DEFAULT_TRANSITION_BEATS: TransitionBeats = 16;
export const DEFAULT_GAIN_DB = 0;
export const DEFAULT_CROSSFADE_BIAS = 0;

/**
 * Reasonable equivalent tempo interpretations for Song B relative to its
 * raw analyzed BPM — tempo trackers sometimes report the same musical
 * pulse at half or double speed. This only scales what the *renderer*
 * treats as Song B's tempo; the raw analyzed BPM is never overwritten and
 * stays visible in the UI separately. Not yet exposed as its own slider —
 * it's set only by the suggestion flow (default 1 otherwise).
 *
 * Deliberately NOT part of MixSettings/DEFAULT_MIX_SETTINGS: it's the
 * planner's tempo *interpretation* of the loaded tracks, not an ordinary
 * user-facing mix control, so "Reset mix settings" must never silently
 * change it back to 1 and break tempo matching. It only resets when a
 * fresh plan is created (new track pair) or a new suggestion is applied.
 */
export type SongBTempoMultiplier = 0.5 | 1 | 2;
export const DEFAULT_SONG_B_TEMPO_MULTIPLIER: SongBTempoMultiplier = 1;

/**
 * "smooth" crossfades the complete spectrum of both songs (M7 behavior,
 * unchanged). "bass_swap" keeps mids/highs on the same crossfade but gives
 * bass ownership its own, narrower swap window — see bassSwapPosition/
 * bassSwapWidthBeats below.
 */
export type TransitionStyle = "smooth" | "bass_swap";
export type BassSwapWidthBeats = 2 | 4 | 8;

export const TRANSITION_STYLE_OPTIONS: readonly TransitionStyle[] = [
  "smooth",
  "bass_swap",
];
export const BASS_SWAP_WIDTH_BEATS_OPTIONS: readonly BassSwapWidthBeats[] = [2, 4, 8];

export const DEFAULT_TRANSITION_STYLE: TransitionStyle = "smooth";
export const DEFAULT_BASS_SWAP_POSITION = 0.5;
export const DEFAULT_BASS_SWAP_WIDTH_BEATS: BassSwapWidthBeats = 4;

/**
 * The transition plan is the shared, authoritative editor state that both
 * the automatic transition generator (manual or suggested) and the manual
 * editor read from and write to. Anchors are set via the waveform
 * (click-to-seek), the editor's own previous/next controls, or a suggested
 * plan; all write to the *same* anchor fields here, there is no separate
 * "editor anchor" or "suggested anchor."
 */
export interface TransitionPlan {
  songAAnchor: BeatAnchor | null;
  songBAnchor: BeatAnchor | null;
  transitionBeats: TransitionBeats;
  songAGainDb: number;
  songBGainDb: number;
  crossfadeBias: number;
  songBTempoMultiplier: SongBTempoMultiplier;
  transitionStyle: TransitionStyle;
  /** Normalized position through the full transition: 0 = start, 0.5 =
   * the aligned anchor, 1 = end. Only meaningful when transitionStyle is
   * "bass_swap" — ignored (but always present/valid) for "smooth". */
  bassSwapPosition: number;
  bassSwapWidthBeats: BassSwapWidthBeats;
}

/**
 * Only the user-facing mix fields — what "Reset mix settings" restores.
 * Deliberately excludes songBTempoMultiplier (the planner's tempo
 * interpretation, not a user mix control — see its doc comment above) and
 * the anchors (never touched by a mix-settings reset).
 */
export type MixSettings = Pick<
  TransitionPlan,
  | "transitionBeats"
  | "songAGainDb"
  | "songBGainDb"
  | "crossfadeBias"
  | "transitionStyle"
  | "bassSwapPosition"
  | "bassSwapWidthBeats"
>;

export const DEFAULT_MIX_SETTINGS: MixSettings = {
  transitionBeats: DEFAULT_TRANSITION_BEATS,
  songAGainDb: DEFAULT_GAIN_DB,
  songBGainDb: DEFAULT_GAIN_DB,
  crossfadeBias: DEFAULT_CROSSFADE_BIAS,
  transitionStyle: DEFAULT_TRANSITION_STYLE,
  bassSwapPosition: DEFAULT_BASS_SWAP_POSITION,
  bassSwapWidthBeats: DEFAULT_BASS_SWAP_WIDTH_BEATS,
};

export function createInitialTransitionPlan(): TransitionPlan {
  return {
    songAAnchor: null,
    songBAnchor: null,
    songBTempoMultiplier: DEFAULT_SONG_B_TEMPO_MULTIPLIER,
    ...DEFAULT_MIX_SETTINGS,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function clampGainDb(value: number): number {
  return clamp(value, GAIN_DB_MIN, GAIN_DB_MAX);
}

export function clampCrossfadeBias(value: number): number {
  return clamp(value, CROSSFADE_BIAS_MIN, CROSSFADE_BIAS_MAX);
}

/**
 * The inclusive [min, max] range of `bassSwapPosition` values for which
 * the whole bass-swap window fits inside the transition — mirrors the
 * backend's `_valid_bass_swap_range` exactly, so the two can never
 * disagree about what's valid.
 */
export function validBassSwapRange(
  transitionBeats: TransitionBeats,
  bassSwapWidthBeats: BassSwapWidthBeats,
): [number, number] {
  const halfWidth = bassSwapWidthBeats / (2 * transitionBeats);
  return [halfWidth, 1 - halfWidth];
}

/** Clamps a bass-swap position into the valid range for the given
 * transition length/width, so a length or width change can never leave
 * the plan pointing at a now-invalid position. */
export function clampBassSwapPosition(
  value: number,
  transitionBeats: TransitionBeats,
  bassSwapWidthBeats: BassSwapWidthBeats,
): number {
  const [min, max] = validBassSwapRange(transitionBeats, bassSwapWidthBeats);
  return clamp(value, min, max);
}

/** Beat offset relative to the aligned anchor (negative = earlier, positive
 * = later) — the user-facing equivalent of a normalized bassSwapPosition. */
export function bassSwapOffsetBeats(
  bassSwapPosition: number,
  transitionBeats: TransitionBeats,
): number {
  return (bassSwapPosition - 0.5) * transitionBeats;
}
