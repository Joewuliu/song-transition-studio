"use client";

import { useState } from "react";
import { useWaveSurfer } from "@/hooks/useWaveSurfer";
import type { TransitionPreviewState } from "@/hooks/useTransitionPreview";
import { formatDuration } from "@/lib/audio";
import { downloadTransition, sanitizeExportFilename } from "@/lib/export";
import type { TransitionBeats } from "@/lib/transitionPlan";
import { CheckIcon, PauseIcon, PlayIcon } from "@/components/icons";

const PREVIEW_WAVE_COLOR = "#8d8991";
const PREVIEW_PROGRESS_COLOR = "#faf9fa";
const PREVIEW_WAVEFORM_HEIGHT = 88;

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
  return (
    <section
      aria-labelledby="preview-heading"
      className="flex flex-col gap-4 rounded-2xl bg-ed-surface p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <h2 id="preview-heading" className="text-sm font-semibold text-ed-strong">
          Preview
        </h2>
        <PreviewSteps state={state} />
      </div>

      <div aria-live="polite">
        {state.status === "idle" && (
          <p className="text-[13px] text-ed-muted">
            Adjust the mix, then generate a preview to listen before you export.
          </p>
        )}
        {state.status === "generating" && (
          <p className="text-[13px] text-ed-muted">Generating transition…</p>
        )}
        {state.status === "error" && (
          <p className="text-[13px] text-ed-danger">{state.message}</p>
        )}
      </div>

      {state.status === "success" && (
        <>
          {state.isStale ? (
            <div
              aria-live="polite"
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[color-mix(in_oklab,var(--ed-amber)_14%,transparent)] px-3.5 py-3"
            >
              <p className="text-[13px] text-ed-text">
                <span className="font-semibold text-ed-amber">Preview out of date</span> — the
                audio below is from your previous settings. Regenerate preview to export.
              </p>
              <button
                type="button"
                onClick={onRegenerate}
                className="ed-btn ed-btn-secondary min-h-9"
              >
                Regenerate preview
              </button>
            </div>
          ) : (
            <p
              aria-live="polite"
              className="flex items-center gap-2 text-[13px] text-ed-text"
            >
              <CheckIcon className="size-4 text-ed-strong" />
              Preview matches current settings
            </p>
          )}
          <PreviewPlayer
            key={`player-${state.generation}`}
            file={state.file}
            targetBpm={state.targetBpm}
            durationSeconds={state.durationSeconds}
            transitionBeats={state.transitionBeats}
          />
          {!state.isStale && (
            <ExportControl
              key={`export-${state.generation}`}
              file={state.file}
              defaultFilename={defaultFilename}
            />
          )}
        </>
      )}
    </section>
  );
}

const PREVIEW_STEPS = ["Generate", "Listen", "Export"] as const;

/** Where the user is in Generate → Listen → Export, derived entirely from
 * the preview state itself. A fresh preview means generating is done and
 * the export is the next move; everything else still needs a (re)generate. */
function PreviewSteps({ state }: { state: TransitionPreviewState }) {
  const current = state.status === "success" && !state.isStale ? 2 : 0;

  return (
    <ol aria-label="Preview steps" className="flex items-center gap-x-4 text-xs">
      {PREVIEW_STEPS.map((step, index) => {
        const isDone = index < current;
        const isCurrent = index === current;
        return (
          <li
            key={step}
            className={`flex items-center gap-1.5 ${
              isCurrent
                ? "font-semibold text-ed-strong"
                : isDone
                  ? "text-ed-muted"
                  : "text-ed-faint"
            }`}
          >
            {isDone ? (
              <CheckIcon className="size-3.5" />
            ) : (
              <span
                aria-hidden="true"
                className={`size-1.5 rounded-full ${
                  isCurrent ? "bg-current" : "border border-current"
                }`}
              />
            )}
            {step}
            {isCurrent && <span className="sr-only"> (current step)</span>}
          </li>
        );
      })}
    </ol>
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
    height: PREVIEW_WAVEFORM_HEIGHT,
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlay}
          disabled={!isReady}
          data-playing={isPlaying}
          data-tone="neutral"
          aria-label={isPlaying ? "Pause preview" : "Play preview"}
          className="ed-transport"
        >
          {isPlaying ? (
            <PauseIcon className="size-[18px]" />
          ) : (
            <PlayIcon className="size-[18px]" />
          )}
        </button>
        <div className="ed-well relative min-w-0 flex-1 p-2">
          <div
            ref={containerRef}
            className="w-full"
            style={{ minHeight: PREVIEW_WAVEFORM_HEIGHT }}
          />
          {!isReady && (
            <p
              role="status"
              className="absolute inset-0 grid place-items-center text-xs text-ed-muted"
            >
              Decoding preview…
            </p>
          )}
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
        <PreviewReadout label="Length" value={`${transitionBeats} beats`} />
        <PreviewReadout label="Target" value={`${targetBpm.toFixed(1)} BPM`} />
        <PreviewReadout label="Preview" value={formatDuration(durationSeconds)} />
      </dl>
    </div>
  );
}

function PreviewReadout({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="text-xs text-ed-muted">{label}</dt>
      <dd className="font-mono tabular-nums text-ed-strong">{value}</dd>
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
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <label className="flex min-w-0 flex-1 flex-col gap-1.5 text-[13px] font-medium text-ed-muted">
        Filename
        <input
          type="text"
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          onBlur={() => setFilename((current) => sanitizeExportFilename(current))}
          spellCheck={false}
          className="ed-input"
        />
      </label>
      <button
        type="button"
        onClick={handleExport}
        className="ed-btn ed-btn-primary min-h-10 sm:shrink-0"
      >
        Export WAV
      </button>
    </div>
  );
}
