"use client";

import { useCallback, useRef, useState } from "react";
import {
  renderTransition,
  RenderTransitionError,
  type TrackAnalysis,
  type TransitionVariant,
  type TransitionVariantId,
} from "@/lib/api";
import type { TransitionBeats } from "@/lib/transitionPlan";

export type VariantPreviewState =
  | { status: "idle" }
  | { status: "rendering"; variantId: TransitionVariantId }
  | {
      status: "success";
      variantId: TransitionVariantId;
      /** Bumped on every successful render; use as a remount key for the
       * player so its internal ready/duration state always starts fresh. */
      generation: number;
      file: File;
      targetBpm: number;
      durationSeconds: number;
      transitionBeats: TransitionBeats;
    }
  | { status: "error"; variantId: TransitionVariantId; message: string };

interface PreviewVariantArgs {
  variant: TransitionVariant;
  songAFile: File;
  songBFile: File;
  songAAnalysis: TrackAnalysis;
  songBAnalysis: TrackAnalysis;
}

interface UseVariantPreviewResult {
  state: VariantPreviewState;
  /** Renders exactly the given variant's plan. A no-op if that same
   * variant is already rendering — never issues duplicate concurrent
   * requests for one option. Switching to a different variant while one
   * is in flight is allowed; only the latest request's result is kept. */
  previewVariant: (args: PreviewVariantArgs) => void;
  reset: () => void;
}

/**
 * Option-preview state — auditioning a candidate TransitionVariant before
 * it's adopted. Deliberately separate from useTransitionPreview, which
 * owns the *editable* plan's own preview once a variant (or a manual
 * choice) has been adopted into the editor; the two are never the same
 * player representing the same "live" plan (see M9 notes).
 */
export function useVariantPreview(): UseVariantPreviewResult {
  const [state, setState] = useState<VariantPreviewState>({ status: "idle" });
  const nextGeneration = useRef(0);
  const renderingVariantId = useRef<TransitionVariantId | null>(null);
  const latestRequestId = useRef(0);

  const previewVariant = useCallback(
    ({ variant, songAFile, songBFile, songAAnalysis, songBAnalysis }: PreviewVariantArgs) => {
      if (renderingVariantId.current === variant.id) return;

      renderingVariantId.current = variant.id;
      const requestId = ++latestRequestId.current;
      setState({ status: "rendering", variantId: variant.id });

      void renderTransition({
        songAFile,
        songBFile,
        songAAnchor: variant.plan.songAAnchor,
        songBAnchor: variant.plan.songBAnchor,
        songABpm: songAAnalysis.tempoBpm,
        songBBpm: songBAnalysis.tempoBpm,
        transitionBeats: variant.plan.transitionBeats,
        songAGainDb: variant.plan.songAGainDb,
        songBGainDb: variant.plan.songBGainDb,
        crossfadeBias: variant.plan.crossfadeBias,
        songBTempoMultiplier: variant.plan.songBTempoMultiplier,
        transitionStyle: variant.plan.transitionStyle,
        bassSwapPosition: variant.plan.bassSwapPosition,
        bassSwapWidthBeats: variant.plan.bassSwapWidthBeats,
      }).then(
        (result) => {
          if (renderingVariantId.current === variant.id) {
            renderingVariantId.current = null;
          }
          if (requestId !== latestRequestId.current) return;

          nextGeneration.current += 1;
          const file = new File([result.wavBlob], `${variant.id}-preview.wav`, {
            type: "audio/wav",
          });
          setState({
            status: "success",
            variantId: variant.id,
            generation: nextGeneration.current,
            file,
            targetBpm: result.targetBpm ?? songAAnalysis.tempoBpm,
            durationSeconds: result.durationSeconds ?? 0,
            transitionBeats: variant.plan.transitionBeats,
          });
        },
        (error: unknown) => {
          if (renderingVariantId.current === variant.id) {
            renderingVariantId.current = null;
          }
          if (requestId !== latestRequestId.current) return;

          const message =
            error instanceof RenderTransitionError
              ? error.message
              : "Failed to preview this option.";
          setState({ status: "error", variantId: variant.id, message });
        },
      );
    },
    [],
  );

  const reset = useCallback(() => {
    renderingVariantId.current = null;
    // Invalidate any in-flight request so its eventual resolution can't
    // resurrect stale state after this reset (e.g. right after adopting a
    // variant while a different one was still rendering).
    latestRequestId.current += 1;
    setState((current) => (current.status === "idle" ? current : { status: "idle" }));
  }, []);

  return { state, previewVariant, reset };
}
