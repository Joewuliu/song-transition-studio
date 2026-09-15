"use client";

import { useCallback } from "react";
import { findNearestBeatIndex } from "@/lib/beats";
import type { BeatAnchor } from "@/lib/transitionPlan";

interface UseBeatAnchorControlsOptions {
  beats: number[];
  anchor: BeatAnchor | null;
  onAnchorChange: (anchor: BeatAnchor | null) => void;
}

interface UseBeatAnchorControlsResult {
  selectedIndex: number | null;
  selectedTime: number | null;
  selectNearest: (timeSeconds: number) => void;
  selectPrevious: () => void;
  selectNext: () => void;
  canSelectPrevious: boolean;
  canSelectNext: boolean;
}

/**
 * The anchor value itself is owned by the caller (it's shared transition
 * state, needed by both Song A and Song B at once) — this hook just wraps
 * it with the beat-indexed selection operations a track's UI needs.
 */
export function useBeatAnchorControls({
  beats,
  anchor,
  onAnchorChange,
}: UseBeatAnchorControlsOptions): UseBeatAnchorControlsResult {
  const selectedIndex = anchor?.beatIndex ?? null;
  const selectedTime = anchor?.timeSeconds ?? null;

  const selectIndex = useCallback(
    (index: number) => {
      if (beats.length === 0) return;
      const clamped = Math.min(Math.max(index, 0), beats.length - 1);
      onAnchorChange({ beatIndex: clamped, timeSeconds: beats[clamped] });
    },
    [beats, onAnchorChange],
  );

  const selectNearest = useCallback(
    (timeSeconds: number) => {
      const index = findNearestBeatIndex(beats, timeSeconds);
      if (index !== null) selectIndex(index);
    },
    [beats, selectIndex],
  );

  const selectPrevious = useCallback(() => {
    if (selectedIndex === null || selectedIndex <= 0) return;
    selectIndex(selectedIndex - 1);
  }, [selectedIndex, selectIndex]);

  const selectNext = useCallback(() => {
    selectIndex(selectedIndex === null ? 0 : selectedIndex + 1);
  }, [selectedIndex, selectIndex]);

  return {
    selectedIndex,
    selectedTime,
    selectNearest,
    selectPrevious,
    selectNext,
    canSelectPrevious: selectedIndex !== null && selectedIndex > 0,
    canSelectNext:
      beats.length > 0 && (selectedIndex === null || selectedIndex < beats.length - 1),
  };
}
