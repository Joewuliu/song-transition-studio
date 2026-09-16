"use client";

import { useWaveSurfer } from "@/hooks/useWaveSurfer";
import type { TransitionPreviewState } from "@/hooks/useTransitionPreview";
import { formatDuration } from "@/lib/audio";
import { TRANSITION_BEATS } from "@/lib/transitionPlan";
import { PauseIcon, PlayIcon } from "@/components/icons";

const PREVIEW_WAVE_COLOR = "#a1a1aa";
const PREVIEW_PROGRESS_COLOR = "#52525b";

interface TransitionPreviewPanelProps {
  state: TransitionPreviewState;
}

export function TransitionPreviewPanel({ state }: TransitionPreviewPanelProps) {
  if (state.status === "idle") return null;

  return (
    <section className="flex flex-col gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
      <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Transition preview
      </h2>

      {state.status === "generating" && (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Generating transition…
        </p>
      )}

      {state.status === "error" && (
        <p className="text-sm text-red-500">{state.message}</p>
      )}

      {state.status === "success" && (
        <PreviewPlayer
          key={state.generation}
          file={state.file}
          targetBpm={state.targetBpm}
          durationSeconds={state.durationSeconds}
        />
      )}
    </section>
  );
}

function PreviewPlayer({
  file,
  targetBpm,
  durationSeconds,
}: {
  file: File;
  targetBpm: number;
  durationSeconds: number;
}) {
  const { containerRef, isReady, isPlaying, togglePlay } = useWaveSurfer({
    file,
    waveColor: PREVIEW_WAVE_COLOR,
    progressColor: PREVIEW_PROGRESS_COLOR,
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={togglePlay}
          disabled={!isReady}
          aria-label={isPlaying ? "Pause" : "Play"}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-zinc-300 text-zinc-700 transition-colors hover:border-zinc-400 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-200"
        >
          {isPlaying ? (
            <PauseIcon className="h-4 w-4" />
          ) : (
            <PlayIcon className="h-4 w-4" />
          )}
        </button>
        <div className="min-w-0 flex-1">
          <div ref={containerRef} className="w-full" />
          {!isReady && (
            <p className="text-xs text-zinc-400">Decoding preview…</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
        <span>{TRANSITION_BEATS} beats</span>
        <span>Target: {targetBpm.toFixed(1)} BPM</span>
        <span>{formatDuration(durationSeconds)} preview</span>
      </div>
    </div>
  );
}
