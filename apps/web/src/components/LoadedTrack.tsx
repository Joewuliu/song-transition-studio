"use client";

import { useWaveSurfer } from "@/hooks/useWaveSurfer";
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
    </div>
  );
}
