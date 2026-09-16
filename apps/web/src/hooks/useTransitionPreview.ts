"use client";

import { useCallback, useRef, useState } from "react";
import {
  renderTransition,
  RenderTransitionError,
  type TrackAnalysis,
} from "@/lib/api";
import type {
  BassSwapWidthBeats,
  BeatAnchor,
  SongBTempoMultiplier,
  TransitionBeats,
  TransitionStyle,
} from "@/lib/transitionPlan";

export type TransitionPreviewState =
  | { status: "idle" }
  | { status: "generating" }
  | {
      status: "success";
      /** Bumped on every successful render; use as a remount key for the
       * WaveSurfer-backed player so its internal ready/duration state
       * always starts fresh for the new preview. */
      generation: number;
      file: File;
      targetBpm: number;
      durationSeconds: number;
      transitionBeats: TransitionBeats;
      /** True once a plan edit (anchor, length, gain, bias) has happened
       * since this preview was rendered. The audio itself is untouched and
       * still playable — only the label/CTA around it changes. */
      isStale: boolean;
    }
  | { status: "error"; message: string };

interface GenerateArgs {
  songAFile: File;
  songBFile: File;
  songAAnalysis: TrackAnalysis;
  songBAnalysis: TrackAnalysis;
  songAAnchor: BeatAnchor;
  songBAnchor: BeatAnchor;
  transitionBeats: TransitionBeats;
  songAGainDb: number;
  songBGainDb: number;
  crossfadeBias: number;
  songBTempoMultiplier: SongBTempoMultiplier;
  transitionStyle: TransitionStyle;
  bassSwapPosition: number;
  bassSwapWidthBeats: BassSwapWidthBeats;
}

interface UseTransitionPreviewResult {
  state: TransitionPreviewState;
  generate: (args: GenerateArgs) => void;
  /** Marks an existing successful preview as out of date without removing
   * it (anchor/mix-setting edits) — a no-op for every other state. */
  markStale: () => void;
  /** Fully discards the preview (source track/analysis changed). */
  reset: () => void;
}

/**
 * The rendered preview is wrapped as a File (not a bare object URL) so
 * playback can reuse useWaveSurfer's existing, already-correct object-URL
 * lifecycle rather than inventing a second one here.
 */
export function useTransitionPreview(): UseTransitionPreviewResult {
  const [state, setState] = useState<TransitionPreviewState>({ status: "idle" });
  const nextGeneration = useRef(0);

  const generate = useCallback((args: GenerateArgs) => {
    setState((current) =>
      current.status === "generating" ? current : { status: "generating" },
    );

    void renderTransition({
      songAFile: args.songAFile,
      songBFile: args.songBFile,
      songAAnchor: args.songAAnchor,
      songBAnchor: args.songBAnchor,
      songABpm: args.songAAnalysis.tempoBpm,
      songBBpm: args.songBAnalysis.tempoBpm,
      transitionBeats: args.transitionBeats,
      songAGainDb: args.songAGainDb,
      songBGainDb: args.songBGainDb,
      crossfadeBias: args.crossfadeBias,
      songBTempoMultiplier: args.songBTempoMultiplier,
      transitionStyle: args.transitionStyle,
      bassSwapPosition: args.bassSwapPosition,
      bassSwapWidthBeats: args.bassSwapWidthBeats,
    }).then(
      (result) => {
        nextGeneration.current += 1;
        const file = new File([result.wavBlob], "transition-preview.wav", {
          type: "audio/wav",
        });
        setState({
          status: "success",
          generation: nextGeneration.current,
          file,
          targetBpm: result.targetBpm ?? args.songAAnalysis.tempoBpm,
          durationSeconds: result.durationSeconds ?? 0,
          transitionBeats: args.transitionBeats,
          isStale: false,
        });
      },
      (error: unknown) => {
        const message =
          error instanceof RenderTransitionError
            ? error.message
            : "Failed to generate the transition.";
        setState({ status: "error", message });
      },
    );
  }, []);

  const markStale = useCallback(() => {
    setState((current) =>
      current.status === "success" && !current.isStale
        ? { ...current, isStale: true }
        : current,
    );
  }, []);

  const reset = useCallback(() => {
    setState((current) => (current.status === "idle" ? current : { status: "idle" }));
  }, []);

  return { state, generate, markStale, reset };
}
