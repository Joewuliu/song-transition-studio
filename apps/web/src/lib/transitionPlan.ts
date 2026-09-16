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

/** Fixed for M4 — not yet a user-adjustable parameter. */
export const TRANSITION_BEATS = 16;

/**
 * The transition plan is the shared representation that both the automatic
 * transition generator and the future manual editor read from and write
 * to. Keep it limited to what's actually established so far — later
 * milestones (crossfade curves, EQ, effects) extend this without changing
 * how anchors themselves are represented.
 */
export interface TransitionPlan {
  songAAnchor: BeatAnchor | null;
  songBAnchor: BeatAnchor | null;
  transitionBeats: typeof TRANSITION_BEATS;
}
