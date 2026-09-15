"use client";

import { useWaveSurfer } from "@/hooks/useWaveSurfer";
import { useTrackAnalysis } from "@/hooks/useTrackAnalysis";
import { formatDuration } from "@/lib/audio";
import { PauseIcon, PlayIcon } from "@/components/icons";

interface LoadedTrackProps {
  file: File;
  waveColor: string;
  progressColor: string;
  onReplace: () => void;
  onRemove: () => void;
}

export function LoadedTrack({
  file,
  waveColor,
  progressColor,
  onReplace,
  onRemove,
}: LoadedTrackProps) {
  const { containerRef, isReady, isPlaying, duration, error, togglePlay } =
    useWaveSurfer({ file, waveColor, progressColor });
  const { state: analysisState, analyze } = useTrackAnalysis(file);

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-4">
        <span className="truncate text-sm text-zinc-600 dark:text-zinc-400">
          {file.name}
          {isReady && ` · ${formatDuration(duration)}`}
        </span>
        <div className="flex shrink-0 items-center gap-4 text-xs">
          <button
            type="button"
            onClick={onReplace}
            className="text-zinc-500 transition-colors hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="text-zinc-500 transition-colors hover:text-red-500 dark:text-zinc-400"
          >
            Remove
          </button>
        </div>
      </div>

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
          {!isReady && !error && (
            <p className="text-xs text-zinc-400">Decoding waveform…</p>
          )}
        </div>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <div className="flex flex-col gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
        {analysisState.status === "success" ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
            <span>{analysisState.result.tempoBpm.toFixed(1)} BPM</span>
            <span>{analysisState.result.beatCount} beats</span>
            <span>
              {formatDuration(analysisState.result.durationSeconds)} analyzed
            </span>
          </div>
        ) : (
          <button
            type="button"
            onClick={analyze}
            disabled={analysisState.status === "analyzing"}
            className="self-start rounded-full border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 transition-colors hover:border-zinc-400 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200"
          >
            {analysisState.status === "analyzing"
              ? "Analyzing…"
              : "Analyze track"}
          </button>
        )}

        {analysisState.status === "error" && (
          <p className="text-xs text-red-500">{analysisState.message}</p>
        )}
      </div>
    </div>
  );
}
