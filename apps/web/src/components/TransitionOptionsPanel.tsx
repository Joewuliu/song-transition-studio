"use client";

import { useEffect, useState } from "react";
import type { TransitionSuggestionState } from "@/hooks/useTransitionSuggestion";
import type { VariantPreviewState } from "@/hooks/useVariantPreview";
import type { TransitionVariant } from "@/lib/api";

interface TransitionOptionsPanelProps {
  suggestionState: TransitionSuggestionState;
  onFindTransitions: () => void;
  variantPreviewState: VariantPreviewState;
  onPreviewVariant: (variant: TransitionVariant) => void;
  onUseInEditor: (variant: TransitionVariant) => void;
}

/**
 * Surfaces the M9 transition options (Smooth Blend / Bass Swap / Quick
 * Mix) once both tracks are analyzed. These are immutable suggestions —
 * auditioning one via Preview never touches the editable TransitionPlan;
 * only "Use in editor" does that (see page.tsx's applyVariant).
 */
export function TransitionOptionsPanel({
  suggestionState,
  onFindTransitions,
  variantPreviewState,
  onPreviewVariant,
  onUseInEditor,
}: TransitionOptionsPanelProps) {
  const isAnyVariantRendering = variantPreviewState.status === "rendering";

  return (
    <section className="flex flex-col gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
      <button
        type="button"
        onClick={onFindTransitions}
        disabled={suggestionState.status === "suggesting"}
        className="self-start rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-400 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200"
      >
        {suggestionState.status === "suggesting"
          ? "Finding transitions…"
          : suggestionState.status === "success"
            ? "Find transitions again"
            : "Find transitions"}
      </button>
      <p className="text-xs text-red-500" aria-live="polite">
        {suggestionState.status === "error" ? suggestionState.message : ""}
      </p>

      {suggestionState.status === "success" && (
        <div className="flex flex-col gap-2">
          <h3 className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Transition options
          </h3>
          <div className="flex flex-col gap-2">
            {suggestionState.suggestion.variants.map((variant) => (
              <VariantOption
                key={variant.id}
                variant={variant}
                previewState={variantPreviewState}
                isAnyVariantRendering={isAnyVariantRendering}
                onPreview={() => onPreviewVariant(variant)}
                onUseInEditor={() => onUseInEditor(variant)}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function VariantOption({
  variant,
  previewState,
  isAnyVariantRendering,
  onPreview,
  onUseInEditor,
}: {
  variant: TransitionVariant;
  previewState: VariantPreviewState;
  isAnyVariantRendering: boolean;
  onPreview: () => void;
  onUseInEditor: () => void;
}) {
  const isActive = previewState.status !== "idle" && previewState.variantId === variant.id;
  const isThisRendering = isActive && previewState.status === "rendering";

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
          {variant.name}
        </span>
        <span className="shrink-0 text-xs text-zinc-400">
          {variant.plan.transitionBeats} beats
        </span>
      </div>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{variant.description}</p>

      <div className="mt-0.5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onPreview}
          disabled={isAnyVariantRendering}
          aria-label={`Preview ${variant.name}`}
          className="rounded-full border border-zinc-300 px-3 py-1 text-xs font-medium text-zinc-600 transition-colors hover:border-zinc-400 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300"
        >
          {isThisRendering ? "Loading preview…" : "Preview"}
        </button>
        <button
          type="button"
          onClick={onUseInEditor}
          aria-label={`Use ${variant.name} in editor`}
          className="rounded-full bg-zinc-900 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          Use in editor
        </button>
        <span className="text-xs text-red-500" aria-live="polite">
          {isActive && previewState.status === "error" ? previewState.message : ""}
        </span>
      </div>

      {isActive && previewState.status === "success" && (
        <VariantAudioPlayer
          key={previewState.generation}
          file={previewState.file}
          label={`Previewing: ${variant.name}`}
        />
      )}
    </div>
  );
}

/** Mounted keyed by generation (see VariantOption), so a fresh preview
 * always gets a fresh instance instead of needing a manual reset here. */
function VariantAudioPlayer({ file, label }: { file: File; label: string }) {
  const [url] = useState(() => URL.createObjectURL(file));

  useEffect(() => {
    return () => URL.revokeObjectURL(url);
  }, [url]);

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wide text-zinc-400">{label}</span>
      <audio controls src={url} aria-label={label} className="h-8 w-full" />
    </div>
  );
}
