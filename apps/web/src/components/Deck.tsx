"use client";

import {
  useCallback,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
} from "react";
import { useWaveSurfer } from "@/hooks/useWaveSurfer";
import { useTrackAnalysis } from "@/hooks/useTrackAnalysis";
import { useBeatAnchorControls } from "@/hooks/useBeatAnchorControls";
import { formatDuration, formatTimestamp, isSupportedAudioFile } from "@/lib/audio";
import { EMPTY_BEATS, toDisplayBeatNumber } from "@/lib/beats";
import { EDITOR_TRACK_STYLES, type TrackAccent } from "@/lib/trackAccent";
import type { TrackAnalysis } from "@/lib/api";
import type { BeatAnchor } from "@/lib/transitionPlan";
import { BeatGrid } from "@/components/BeatGrid";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PauseIcon,
  PlayIcon,
} from "@/components/icons";

const DECK_WAVEFORM_HEIGHT = 144;

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
 * One deck of the editor: the same file/WaveSurfer/beat-grid/anchor
 * machinery as the setup page (via the same hooks), presented so the
 * waveform and transport lead. The deck carries its song's identity color
 * (violet = Song A, teal = Song B); Replace, Remove and Re-analyze stay
 * available but quiet.
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
  const styles = EDITOR_TRACK_STYLES[accent];
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

  const isAnalyzing = analysisState.status === "analyzing";
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
    <section
      aria-label={deckLabel}
      className="flex min-w-0 flex-col gap-4 rounded-2xl bg-ed-surface p-4 sm:p-5"
      style={{ "--track": styles.color } as CSSProperties}
    >
      <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <div className="min-w-0 flex-1 basis-44">
          <p className={`flex items-center gap-2 text-xs font-medium ${styles.textClass}`}>
            <span aria-hidden="true" className="size-2 rounded-full bg-current" />
            {deckLabel}
          </p>
          <h2
            className="mt-1 truncate text-[15px] font-semibold text-ed-strong"
            title={file.name}
          >
            {file.name}
          </h2>
          <div aria-live="polite" className="text-xs text-ed-danger">
            {error ?? fileError}
          </div>
        </div>
        <div className="-mr-2 flex items-center">
          <button
            type="button"
            onClick={analyze}
            disabled={isAnalyzing}
            aria-label={isAnalyzing ? `Analyzing ${deckLabel}` : `Re-analyze ${deckLabel}`}
            className="ed-btn-ghost"
          >
            {isAnalyzing ? "Analyzing…" : "Re-analyze"}
          </button>
          <button
            type="button"
            onClick={openFileDialog}
            aria-label={`Replace ${deckLabel} track`}
            className="ed-btn-ghost"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={() => onFileChange(null)}
            aria-label={`Remove ${deckLabel} track`}
            className="ed-btn-ghost"
          >
            Remove
          </button>
        </div>
      </header>
      <input
        ref={inputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={handleInputChange}
      />

      {analysis && (
        <dl className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
          <Readout label="BPM" value={analysis.tempoBpm.toFixed(1)} mono />
          {analysis.estimatedKey && analysis.estimatedMode && (
            <Readout label="Key" value={`${analysis.estimatedKey} ${analysis.estimatedMode}`} />
          )}
          <Readout label="Duration" value={formatDuration(analysis.durationSeconds)} mono />
        </dl>
      )}

      <div className="ed-well relative overflow-hidden p-2">
        <div className="relative" style={{ minHeight: DECK_WAVEFORM_HEIGHT }}>
          <div ref={containerRef} className="w-full" />
          {analysis && (
            <BeatGrid
              beats={beats}
              duration={duration}
              selectedIndex={selectedIndex}
              markerClassName="bg-white/15"
              selectedMarkerClassName="bg-ed-amber"
            />
          )}
          {!isReady && !error && (
            <p
              role="status"
              className="absolute inset-0 grid place-items-center text-xs text-ed-muted"
            >
              Decoding waveform…
            </p>
          )}
        </div>
      </div>

      {/* Transport and anchor are always two rows so both decks line up,
          whatever the anchor label's length or the deck's width. */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={togglePlay}
            disabled={!isReady}
            data-playing={isPlaying}
            aria-label={`${isPlaying ? "Pause" : "Play"} ${deckLabel}`}
            className="ed-transport"
          >
            {isPlaying ? (
              <PauseIcon className="size-[18px]" />
            ) : (
              <PlayIcon className="size-[18px]" />
            )}
          </button>
          <p className="font-mono text-[15px] tabular-nums" aria-hidden="true">
            <span className="text-ed-strong">{formatTimestamp(currentTime)}</span>
            <span className="text-ed-muted"> / {formatDuration(duration)}</span>
          </p>
        </div>

        {analysis ? (
          <div role="group" aria-label={`${deckLabel} anchor`} className="flex items-center gap-2">
            <button
              type="button"
              onClick={selectPrevious}
              disabled={!canSelectPrevious}
              aria-label={`${deckLabel}: select previous beat`}
              className="ed-icon-btn"
            >
              <ChevronLeftIcon className="size-4" />
            </button>
            <p className="flex min-w-0 items-center gap-2 text-[13px]">
              <span aria-hidden="true" className="size-2 shrink-0 rotate-45 bg-ed-amber" />
              {selectedIndex !== null && selectedTime !== null ? (
                <span className="font-mono tabular-nums text-ed-strong">
                  Beat {toDisplayBeatNumber(selectedIndex)} · {formatTimestamp(selectedTime)}
                </span>
              ) : (
                <span className="text-ed-muted">Click the waveform to set an anchor</span>
              )}
            </p>
            <button
              type="button"
              onClick={selectNext}
              disabled={!canSelectNext}
              aria-label={`${deckLabel}: select next beat`}
              className="ed-icon-btn"
            >
              <ChevronRightIcon className="size-4" />
            </button>
          </div>
        ) : (
          <p className="text-xs text-ed-muted">Not analyzed yet.</p>
        )}
      </div>
    </section>
  );
}

function Readout({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-xs text-ed-muted">{label}</dt>
      <dd
        className={`text-[15px] text-ed-strong ${mono ? "font-mono tabular-nums" : "font-medium"}`}
      >
        {value}
      </dd>
    </div>
  );
}
