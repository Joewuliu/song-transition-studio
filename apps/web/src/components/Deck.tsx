"use client";

import { useCallback, useRef, useState, type ChangeEvent } from "react";
import { useWaveSurfer } from "@/hooks/useWaveSurfer";
import { useTrackAnalysis } from "@/hooks/useTrackAnalysis";
import { useBeatAnchorControls } from "@/hooks/useBeatAnchorControls";
import { formatDuration, formatTimestamp, isSupportedAudioFile } from "@/lib/audio";
import { EMPTY_BEATS, toDisplayBeatNumber } from "@/lib/beats";
import { ACCENT_STYLES, type TrackAccent } from "@/lib/trackAccent";
import type { TrackAnalysis } from "@/lib/api";
import type { BeatAnchor } from "@/lib/transitionPlan";
import { BeatGrid } from "@/components/BeatGrid";
import { PauseIcon, PlayIcon } from "@/components/icons";

const DECK_WAVEFORM_HEIGHT = 128;

interface DeckProps {
  deckLabel: string;
  accent: TrackAccent;
  file: File;
  /** Already-known analysis from shared workspace state, if any — used
   * (not re-derived) so a track analyzed on the setup page shows its
   * beat grid/anchor controls immediately here, without forcing a
   * redundant re-analyze. */
  analysis: TrackAnalysis | null;
  onFileChange: (file: File | null) => void;
  onAnalysisChange: (analysis: TrackAnalysis | null) => void;
  anchor: BeatAnchor | null;
  onAnchorChange: (anchor: BeatAnchor | null) => void;
}

/**
 * A compact digital deck: the same file/WaveSurfer/beat-grid/anchor
 * machinery as the setup page's TrackSlot, reused via the same hooks —
 * just laid out to prioritize the waveform and transport over
 * upload-oriented chrome. Replace/Remove remain available but stay
 * secondary (small, top-right).
 */
export function Deck({
  deckLabel,
  accent,
  file,
  analysis,
  onFileChange,
  onAnalysisChange,
  anchor,
  onAnchorChange,
}: DeckProps) {
  const styles = ACCENT_STYLES[accent];
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  // Anchor revalidation on (re-)analysis mirrors LoadedTrack's own logic
  // exactly: keep the same beat if it's still in range (refreshing its
  // timestamp), otherwise drop it rather than pointing at a stale beat.
  const handleAnalysisSuccess = useCallback(
    (result: TrackAnalysis) => {
      if (anchor) {
        if (anchor.beatIndex >= result.beats.length) {
          onAnchorChange(null);
        } else {
          const refreshedTime = result.beats[anchor.beatIndex];
          if (refreshedTime !== anchor.timeSeconds) {
            onAnchorChange({ beatIndex: anchor.beatIndex, timeSeconds: refreshedTime });
          }
        }
      }
      onAnalysisChange(result);
    },
    [anchor, onAnchorChange, onAnalysisChange],
  );

  const { state: analysisState, analyze } = useTrackAnalysis(file, {
    onSuccess: handleAnalysisSuccess,
  });

  const beats = analysis?.beats ?? EMPTY_BEATS;

  const {
    selectedIndex,
    selectedTime,
    selectNearest,
    selectPrevious,
    selectNext,
    canSelectPrevious,
    canSelectNext,
  } = useBeatAnchorControls({ beats, anchor, onAnchorChange });

  const { containerRef, isReady, isPlaying, duration, currentTime, error, togglePlay } =
    useWaveSurfer({
      file,
      waveColor: styles.wave,
      progressColor: styles.progress,
      height: DECK_WAVEFORM_HEIGHT,
      onSeek: selectNearest,
    });

  const openFileDialog = () => inputRef.current?.click();

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const candidate = event.target.files?.[0];
    event.target.value = "";
    if (!candidate) return;
    if (!isSupportedAudioFile(candidate)) {
      setFileError(`"${candidate.name}" isn't a supported audio file.`);
      return;
    }
    setFileError(null);
    onFileChange(candidate);
  };

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-zinc-200 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-950/40">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span
            className={`text-xs font-semibold uppercase tracking-widest ${styles.text}`}
          >
            {deckLabel}
          </span>
          <span className="truncate text-sm font-medium text-zinc-800 dark:text-zinc-100">
            {file.name}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3 pt-0.5 text-[11px] text-zinc-400">
          <button
            type="button"
            onClick={analyze}
            disabled={analysisState.status === "analyzing"}
            className="transition-colors hover:text-zinc-600 disabled:opacity-50 dark:hover:text-zinc-300"
          >
            {analysisState.status === "analyzing" ? "Analyzing…" : "Re-analyze"}
          </button>
          <button
            type="button"
            onClick={openFileDialog}
            className="transition-colors hover:text-zinc-600 dark:hover:text-zinc-300"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={() => onFileChange(null)}
            className="transition-colors hover:text-red-500"
          >
            Remove
          </button>
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={handleInputChange}
      />

      {analysis && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
          <span className="font-medium tabular-nums text-zinc-700 dark:text-zinc-200">
            {analysis.tempoBpm.toFixed(1)} BPM
          </span>
          {analysis.estimatedKey && analysis.estimatedMode && (
            <span>
              {analysis.estimatedKey} {analysis.estimatedMode}
            </span>
          )}
          <span>{formatDuration(analysis.durationSeconds)}</span>
        </div>
      )}

      <div className="relative">
        <div ref={containerRef} className="w-full" />
        {analysis && (
          <BeatGrid beats={beats} duration={duration} selectedIndex={selectedIndex} />
        )}
      </div>

      <div
        className="flex items-center justify-between text-[11px] tabular-nums text-zinc-400"
        aria-hidden="true"
      >
        <span>{formatTimestamp(currentTime)}</span>
        <span>{formatDuration(duration)}</span>
      </div>

      <p className="text-xs text-red-500" aria-live="polite">
        {error ?? fileError}
      </p>

      {analysis ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={selectPrevious}
              disabled={!canSelectPrevious}
              aria-label="Select previous beat"
              className="flex h-6 w-6 items-center justify-center rounded-full border border-zinc-300 text-sm leading-none text-zinc-600 transition-colors hover:border-zinc-400 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-300"
            >
              ‹
            </button>
            <button
              type="button"
              onClick={selectNext}
              disabled={!canSelectNext}
              aria-label="Select next beat"
              className="flex h-6 w-6 items-center justify-center rounded-full border border-zinc-300 text-sm leading-none text-zinc-600 transition-colors hover:border-zinc-400 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-300"
            >
              ›
            </button>
          </div>
          <span>
            {selectedIndex !== null && selectedTime !== null
              ? `Beat ${toDisplayBeatNumber(selectedIndex)} · ${formatTimestamp(selectedTime)}`
              : "Click the waveform, or use the buttons, to set a transition anchor"}
          </span>
        </div>
      ) : (
        <p className="text-xs text-zinc-400">
          {!isReady ? "Decoding waveform…" : "Not analyzed yet."}
        </p>
      )}

      <button
        type="button"
        onClick={togglePlay}
        disabled={!isReady}
        aria-label={isPlaying ? "Pause" : "Play"}
        className="flex h-11 items-center justify-center gap-2 self-stretch rounded-full border border-zinc-300 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-400 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-200"
      >
        {isPlaying ? (
          <PauseIcon className="h-4 w-4" />
        ) : (
          <PlayIcon className="h-4 w-4" />
        )}
        {isPlaying ? "Pause" : "Play"}
      </button>
    </section>
  );
}
