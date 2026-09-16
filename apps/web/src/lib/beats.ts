const MAX_VISIBLE_BEAT_MARKERS = 240;

/** Stable empty-array reference so hooks/components depending on a track's
 * beats don't churn every render while no analysis result exists yet. */
export const EMPTY_BEATS: readonly number[] = [];

/**
 * Finds the index of the beat closest to `timeSeconds`. `beats` must be
 * ascending (guaranteed by the analysis API), so this runs as a binary
 * search rather than a linear scan.
 */
export function findNearestBeatIndex(
  beats: readonly number[],
  timeSeconds: number,
): number | null {
  if (beats.length === 0) return null;

  let low = 0;
  let high = beats.length - 1;

  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (beats[mid] < timeSeconds) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }

  if (
    low > 0 &&
    Math.abs(beats[low - 1] - timeSeconds) <= Math.abs(beats[low] - timeSeconds)
  ) {
    return low - 1;
  }
  return low;
}

/**
 * Picks a subset of beat indices to render as visual markers so very long
 * tracks don't turn into a solid wall of lines. This only affects what's
 * drawn — every beat in `beats` stays selectable via click-to-seek or the
 * previous/next controls regardless of this subset.
 */
export function selectDisplayBeatIndices(
  beats: readonly number[],
  selectedIndex: number | null,
  maxMarkers: number = MAX_VISIBLE_BEAT_MARKERS,
): number[] {
  if (beats.length <= maxMarkers) {
    return beats.map((_, index) => index);
  }

  const step = Math.ceil(beats.length / maxMarkers);
  const indices = new Set<number>();
  for (let i = 0; i < beats.length; i += step) {
    indices.add(i);
  }
  indices.add(beats.length - 1);
  if (selectedIndex !== null) {
    indices.add(selectedIndex);
  }

  return Array.from(indices).sort((a, b) => a - b);
}

/**
 * BeatAnchor.beatIndex stays zero-based internally (it's a direct array
 * index) — this only converts it for user-facing text, so people see
 * "Beat 1" rather than "Beat 0".
 */
export function toDisplayBeatNumber(beatIndex: number): number {
  return beatIndex + 1;
}
