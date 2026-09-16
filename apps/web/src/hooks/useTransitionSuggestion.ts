"use client";

import { useCallback, useState } from "react";
import {
  suggestTransition,
  SuggestTransitionError,
  type TrackAnalysis,
  type TransitionSuggestion,
} from "@/lib/api";

export type TransitionSuggestionState =
  | { status: "idle" }
  | { status: "suggesting" }
  | { status: "success"; suggestion: TransitionSuggestion }
  | { status: "error"; message: string };

interface UseTransitionSuggestionOptions {
  /** Called right when a suggestion succeeds, e.g. to write it into the
   * shared TransitionPlan — deliberately a callback (not a `useEffect`
   * watching `state`) so applying it is just one more step of the same
   * async flow, not a separate render-driven side effect. */
  onSuggested?: (suggestion: TransitionSuggestion) => void;
}

interface UseTransitionSuggestionResult {
  state: TransitionSuggestionState;
  suggest: (songAAnalysis: TrackAnalysis, songBAnalysis: TrackAnalysis) => void;
  /** Clears suggestion metadata — e.g. a track was replaced/removed/
   * reanalyzed, so the suggestion no longer describes the current inputs. */
  clear: () => void;
}

export function useTransitionSuggestion(
  options: UseTransitionSuggestionOptions = {},
): UseTransitionSuggestionResult {
  const { onSuggested } = options;
  const [state, setState] = useState<TransitionSuggestionState>({ status: "idle" });

  const suggest = useCallback(
    (songAAnalysis: TrackAnalysis, songBAnalysis: TrackAnalysis) => {
      setState((current) =>
        current.status === "suggesting" ? current : { status: "suggesting" },
      );

      void suggestTransition(songAAnalysis, songBAnalysis).then(
        (suggestion) => {
          setState({ status: "success", suggestion });
          onSuggested?.(suggestion);
        },
        (error: unknown) => {
          const message =
            error instanceof SuggestTransitionError
              ? error.message
              : "Failed to suggest a transition.";
          setState({ status: "error", message });
        },
      );
    },
    [onSuggested],
  );

  const clear = useCallback(() => {
    setState((current) => (current.status === "idle" ? current : { status: "idle" }));
  }, []);

  return { state, suggest, clear };
}
