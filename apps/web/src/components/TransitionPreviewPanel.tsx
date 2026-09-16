"use client";

import { useState } from "react";
import { useWaveSurfer } from "@/hooks/useWaveSurfer";
import type { TransitionPreviewState } from "@/hooks/useTransitionPreview";
import { formatDuration } from "@/lib/audio";
import { downloadTransition, sanitizeExportFilename } from "@/lib/export";
import type { TransitionBeats } from "@/lib/transitionPlan";
import { PauseIcon, PlayIcon } from "@/components/icons";

const PREVIEW_WAVE_COLOR = "#a1a1aa";
const PREVIEW_PROGRESS_COLOR = "#52525b";

interface TransitionPreviewPanelProps {
  state: TransitionPreviewState;
  onRegenerate: () => void;
  /** Pre-computed from the two source filenames (see lib/export.ts) —
   * this component never needs to know about File objects beyond the
   * rendered preview itself. */
  defaultFilename: string;
}

/**
 * The final output area: this preview IS the exact rendered artifact
 * Export WAV downloads — nothing is re-rendered on export. Export is only
 * ever offered for a preview that's both successful and fresh (never
 * stale/generating/idle/error), so what the user hears here is always
 * exactly what they'd get in the downloaded file.
 */
export function TransitionPreviewPanel({
  state,
  onRegenerate,
  defaultFilename,
}: TransitionPreviewPanelProps) {
  if (state.status === "idle") return null;

  return (
    <section className="flex flex-col gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
      <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Transition preview
      </h2>

      <div aria-live="polite">
        {state.status === "generating" && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Generating transition…
          </p>
        )}

        {state.status === "error" && (
          <p className="text-sm text-red-500">{state.message}</p>
        )}
      </div>

      {state.status === "success" && (
        <>
          {state.isStale ? (
            <div
              aria-live="polite"
              className="flex flex-wrap items-center gap-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-400"
            >
              <span>
                Preview out of date — the audio below is from your previous
                settings. Regenerate preview to export.
              </span>
              <button
                type="button"
                onClick={onRegenerate}
                className="font-medium underline-offset-4 hover:underline"
              >
                Regenerate preview
              </button>
            </div>
          ) : (
            <p
              aria-live="polite"
              className="text-xs text-emerald-600 dark:text-emerald-400"
            >
              ✓ Preview matches current settings
            </p>
          )}
          <PreviewPlayer
            key={state.generation}
            file={state.file}
            targetBpm={state.targetBpm}
            durationSeconds={state.durationSeconds}
            transitionBeats={state.transitionBeats}
          />
          {!state.isStale && (
            <ExportControl
              key={state.generation}
              file={state.file}
              defaultFilename={defaultFilename}
            />
          )}
        </>
      )}
    </section>
  );
}

function PreviewPlayer({
  file,
  targetBpm,
  durationSeconds,
  transitionBeats,
}: {
  file: File;
  targetBpm: number;
  durationSeconds: number;
  transitionBeats: TransitionBeats;
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
        <span>{transitionBeats} beats</span>
        <span>Target: {targetBpm.toFixed(1)} BPM</span>
        <span>{formatDuration(durationSeconds)} preview</span>
      </div>
    </div>
  );
}

/**
 * Exports EXACTLY `file` — the same WAV already playing above, never a
 * fresh render. `filename` is free-text while editing (no fighting the
 * user's typing); it's only normalized to a safe ".wav" name on blur and,
 * regardless of that, again right before every download.
 */
function ExportControl({
  file,
  defaultFilename,
}: {
  file: File;
  defaultFilename: string;
}) {
  const [filename, setFilename] = useState(defaultFilename);

  const handleExport = () => {
    downloadTransition(file, sanitizeExportFilename(filename));
  };

  return (
    <div className="flex flex-col gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
      <label className="flex flex-col gap-1 text-xs text-zinc-600 dark:text-zinc-400">
        Filename
        <input
          type="text"
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          onBlur={() => setFilename((current) => sanitizeExportFilename(current))}
          spellCheck={false}
          className="w-full rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 text-sm text-zinc-800 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:text-zinc-100"
        />
      </label>
      <button
        type="button"
        onClick={handleExport}
        className="self-start rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        Export WAV
      </button>
    </div>
  );
}
