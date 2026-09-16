"use client";

import { useMemo } from "react";
import { selectDisplayBeatIndices } from "@/lib/beats";

interface BeatGridProps {
  beats: readonly number[];
  /** The waveform's own duration (from useWaveSurfer), not the analysis
   * response's duration — markers must line up with what's actually drawn. */
  duration: number;
  selectedIndex: number | null;
}

/**
 * Purely visual: markers carry no pointer handling of their own, so they
 * never intercept WaveSurfer's own click/drag-to-seek behavior. Selecting a
 * beat happens via that same seek interaction (snapped to the nearest beat
 * upstream) or the previous/next controls, not by clicking a marker.
 */
export function BeatGrid({ beats, duration, selectedIndex }: BeatGridProps) {
  const displayIndices = useMemo(
    () => selectDisplayBeatIndices(beats, selectedIndex),
    [beats, selectedIndex],
  );

  if (duration <= 0 || beats.length === 0) return null;

  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden
    >
      {displayIndices.map((index) => {
        const time = beats[index];
        const percent = Math.min(Math.max(time / duration, 0), 1) * 100;
        const isSelected = index === selectedIndex;

        return (
          <span
            key={index}
            className={
              isSelected
                ? "absolute top-0 bottom-0 w-0.5 bg-amber-500"
                : "absolute top-0 bottom-0 w-px bg-zinc-900/25 dark:bg-white/25"
            }
            style={{ left: `${percent}%` }}
          />
        );
      })}
    </div>
  );
}
