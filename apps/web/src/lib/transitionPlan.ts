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
 * for M6 it's set only by the suggestion flow (default 1 otherwise).
 */
export type SongBTempoMultiplier = 0.5 | 1 | 2;
export const DEFAULT_SONG_B_TEMPO_MULTIPLIER: SongBTempoMultiplier = 1;

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
}

/** Only the mix-related fields — what "Reset mix settings" restores. */
export type MixSettings = Pick<
  TransitionPlan,
  | "transitionBeats"
  | "songAGainDb"
  | "songBGainDb"
  | "crossfadeBias"
  | "songBTempoMultiplier"
>;

export const DEFAULT_MIX_SETTINGS: MixSettings = {
  transitionBeats: DEFAULT_TRANSITION_BEATS,
  songAGainDb: DEFAULT_GAIN_DB,
  songBGainDb: DEFAULT_GAIN_DB,
  crossfadeBias: DEFAULT_CROSSFADE_BIAS,
  songBTempoMultiplier: DEFAULT_SONG_B_TEMPO_MULTIPLIER,
};

export function createInitialTransitionPlan(): TransitionPlan {
  return {
    songAAnchor: null,
    songBAnchor: null,
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
