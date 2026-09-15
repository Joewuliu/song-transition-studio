"use client";

import { useCallback, useState } from "react";
import { analyzeTrack, type TrackAnalysis } from "@/lib/api";

export type TrackAnalysisState =
  | { status: "idle" }
  | { status: "analyzing" }
  | { status: "success"; result: TrackAnalysis }
  | { status: "error"; message: string };

interface UseTrackAnalysisResult {
  state: TrackAnalysisState;
  analyze: () => void;
}

/**
 * Mount this hook under a component keyed by a stable per-track identity
 * (the same key used for useWaveSurfer) so replacing or removing a track
 * discards its analysis for free, instead of needing a manual reset.
 */
export function useTrackAnalysis(file: File): UseTrackAnalysisResult {
  const [state, setState] = useState<TrackAnalysisState>({ status: "idle" });

  const analyze = useCallback(() => {
    if (state.status === "analyzing") return;

    setState({ status: "analyzing" });

    void analyzeTrack(file).then(
      (result) => setState({ status: "success", result }),
      (error: unknown) => {
        const message = error instanceof Error ? error.message : "Analysis failed.";
        setState({ status: "error", message });
      },
    );
  }, [file, state.status]);

  return { state, analyze };
}
