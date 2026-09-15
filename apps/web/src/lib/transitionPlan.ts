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

/**
 * The transition plan is the shared representation that both the future
 * automatic transition generator and the future manual editor will read
 * from and write to. Keep it limited to what M3 actually establishes —
 * later milestones (crossfade curves, EQ, tempo, effects) extend this
 * without changing how anchors themselves are represented.
 */
export interface TransitionPlan {
  songAAnchor: BeatAnchor | null;
  songBAnchor: BeatAnchor | null;
}
