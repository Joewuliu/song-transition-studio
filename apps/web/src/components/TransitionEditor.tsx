"use client";

import { formatTimestamp } from "@/lib/audio";
import { toDisplayBeatNumber } from "@/lib/beats";
import { ACCENT_STYLES } from "@/lib/trackAccent";
import {
  CROSSFADE_BIAS_MAX,
  CROSSFADE_BIAS_MIN,
  GAIN_DB_MAX,
  GAIN_DB_MIN,
  TRANSITION_BEATS_OPTIONS,
  type TransitionBeats,
  type TransitionPlan,
} from "@/lib/transitionPlan";
import type { TempoCompatibility } from "@/lib/api";
import { TransitionCurveVisualization } from "@/components/TransitionCurveVisualization";

export interface AnchorControlState {
  selectedIndex: number | null;
  selectedTime: number | null;
  canSelectPrevious: boolean;
  canSelectNext: boolean;
  selectPrevious: () => void;
  selectNext: () => void;
}

export interface SuggestionInfo {
  tempoCompatibility: TempoCompatibility;
  usedTempoNormalization: boolean;
  songBRawBpm: number;
  effectiveSongBBpm: number;
  /** True once any plan field has been manually changed since this
   * suggestion was applied. Only changes the banner's label — the
   * underlying tempo-interpretation metadata stays visible either way. */
  isEdited: boolean;
}

const TEMPO_COMPATIBILITY_LABEL: Record<TempoCompatibility, string> = {
  compatible: "great tempo match",
  moderate: "good tempo match",
  significant: "noticeable tempo adjustment",
  extreme: "large tempo mismatch — results may sound off",
};

interface TransitionEditorProps {
  plan: TransitionPlan;
  suggestionInfo: SuggestionInfo | null;
  songAAnchorControls: AnchorControlState;
  songBAnchorControls: AnchorControlState;
  onTransitionBeatsChange: (beats: TransitionBeats) => void;
  onSongAGainChange: (db: number) => void;
  onSongBGainChange: (db: number) => void;
  onCrossfadeBiasChange: (bias: number) => void;
  onResetMixSettings: () => void;
  onGenerate: () => void;
  isGenerating: boolean;
  isMixAtDefaults: boolean;
}

export function TransitionEditor({
  plan,
  suggestionInfo,
  songAAnchorControls,
  songBAnchorControls,
  onTransitionBeatsChange,
  onSongAGainChange,
  onSongBGainChange,
  onCrossfadeBiasChange,
  onResetMixSettings,
  onGenerate,
  isGenerating,
  isMixAtDefaults,
}: TransitionEditorProps) {
  return (
    <section className="flex flex-col gap-6 border-t border-zinc-200 pt-6 dark:border-zinc-800">
      <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Transition editor
      </h2>

      {suggestionInfo && (
        <div className="flex flex-col gap-1 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            {suggestionInfo.isEdited ? "Edited suggestion" : "Suggested starting point"}{" "}
            — {TEMPO_COMPATIBILITY_LABEL[suggestionInfo.tempoCompatibility]}
          </span>
          {suggestionInfo.usedTempoNormalization && (
            <span>
              Tempo interpretation: {suggestionInfo.songBRawBpm.toFixed(1)} →{" "}
              {suggestionInfo.effectiveSongBBpm.toFixed(1)} BPM
            </span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <AnchorControl
          label="Song A"
          accentClassName={ACCENT_STYLES.violet.text}
          {...songAAnchorControls}
        />
        <AnchorControl
          label="Song B"
          accentClassName={ACCENT_STYLES.teal.text}
          {...songBAnchorControls}
        />
      </div>

      <TransitionCurveVisualization plan={plan} />

      <LengthSelector value={plan.transitionBeats} onChange={onTransitionBeatsChange} />

      <GainSlider
        label="Song A level"
        valueDb={plan.songAGainDb}
        onChange={onSongAGainChange}
      />
      <GainSlider
        label="Song B level"
        valueDb={plan.songBGainDb}
        onChange={onSongBGainChange}
      />

      <BlendTimingSlider value={plan.crossfadeBias} onChange={onCrossfadeBiasChange} />

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={onResetMixSettings}
          disabled={isMixAtDefaults}
          className="text-xs text-zinc-500 underline-offset-4 hover:underline disabled:opacity-40 dark:text-zinc-400"
        >
          Reset mix settings
        </button>
        <button
          type="button"
          onClick={onGenerate}
          disabled={isGenerating}
          className="ml-auto self-start rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {isGenerating ? "Generating transition…" : "Generate preview"}
        </button>
      </div>
    </section>
  );
}

function AnchorControl({
  label,
  accentClassName,
  selectedIndex,
  selectedTime,
  canSelectPrevious,
  canSelectNext,
  selectPrevious,
  selectNext,
}: AnchorControlState & { label: string; accentClassName: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className={`text-xs font-medium ${accentClassName}`}>
        {label} anchor
      </span>
      <span className="text-sm text-zinc-700 dark:text-zinc-300">
        {selectedIndex !== null && selectedTime !== null
          ? `Beat ${toDisplayBeatNumber(selectedIndex)} · ${formatTimestamp(selectedTime)}`
          : "No anchor selected"}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={selectPrevious}
          disabled={!canSelectPrevious}
          aria-label={`Select previous ${label} beat`}
          className="rounded-full border border-zinc-300 px-2.5 py-1 text-xs text-zinc-600 transition-colors hover:border-zinc-400 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-300"
        >
          previous
        </button>
        <button
          type="button"
          onClick={selectNext}
          disabled={!canSelectNext}
          aria-label={`Select next ${label} beat`}
          className="rounded-full border border-zinc-300 px-2.5 py-1 text-xs text-zinc-600 transition-colors hover:border-zinc-400 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-300"
        >
          next
        </button>
      </div>
    </div>
  );
}

function LengthSelector({
  value,
  onChange,
}: {
  value: TransitionBeats;
  onChange: (beats: TransitionBeats) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-zinc-600 dark:text-zinc-400">Length</span>
      <div className="inline-flex w-fit rounded-full border border-zinc-300 p-0.5 dark:border-zinc-700">
        {TRANSITION_BEATS_OPTIONS.map((beats) => (
          <button
            key={beats}
            type="button"
            onClick={() => onChange(beats)}
            aria-pressed={value === beats}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              value === beats
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            }`}
          >
            {beats}
          </button>
        ))}
        <span className="self-center px-2 text-xs text-zinc-400">beats</span>
      </div>
    </div>
  );
}

function GainSlider({
  label,
  valueDb,
  onChange,
}: {
  label: string;
  valueDb: number;
  onChange: (db: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs text-zinc-600 dark:text-zinc-400">
        <span>{label}</span>
        <div className="flex items-center gap-2">
          <span className="tabular-nums">
            {valueDb > 0 ? "+" : ""}
            {valueDb.toFixed(1)} dB
          </span>
          {valueDb !== 0 && (
            <button
              type="button"
              onClick={() => onChange(0)}
              className="text-zinc-400 underline-offset-4 hover:underline dark:text-zinc-500"
            >
              Reset
            </button>
          )}
        </div>
      </div>
      <input
        type="range"
        min={GAIN_DB_MIN}
        max={GAIN_DB_MAX}
        step={0.5}
        value={valueDb}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label={label}
        className="w-full accent-zinc-700 dark:accent-zinc-300"
      />
    </div>
  );
}

function BlendTimingSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (bias: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs text-zinc-600 dark:text-zinc-400">
        <span>Blend timing</span>
        {value !== 0 && (
          <button
            type="button"
            onClick={() => onChange(0)}
            className="text-zinc-400 underline-offset-4 hover:underline dark:text-zinc-500"
          >
            Reset
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-400">
          Early B
        </span>
        <input
          type="range"
          min={CROSSFADE_BIAS_MIN}
          max={CROSSFADE_BIAS_MAX}
          step={0.05}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          aria-label="Blend timing"
          className="w-full accent-zinc-700 dark:accent-zinc-300"
        />
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-400">
          Late B
        </span>
      </div>
    </div>
  );
}
