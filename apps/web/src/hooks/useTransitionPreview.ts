"use client";

import { useCallback, useRef, useState } from "react";
import {
  renderTransition,
  RenderTransitionError,
  type TrackAnalysis,
} from "@/lib/api";
import type { BeatAnchor } from "@/lib/transitionPlan";

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
    }
  | { status: "error"; message: string };

interface GenerateArgs {
  songAFile: File;
  songBFile: File;
  songAAnalysis: TrackAnalysis;
  songBAnalysis: TrackAnalysis;
  songAAnchor: BeatAnchor;
  songBAnchor: BeatAnchor;
}

interface UseTransitionPreviewResult {
  state: TransitionPreviewState;
  generate: (args: GenerateArgs) => void;
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

  const reset = useCallback(() => {
    setState((current) => (current.status === "idle" ? current : { status: "idle" }));
  }, []);

  return { state, generate, reset };
}
