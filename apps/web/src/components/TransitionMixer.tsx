"use client";

import { useId, type CSSProperties, type ReactNode } from "react";
import type { SuggestionInfo } from "@/context/StudioContext";
import type { TransitionPreviewState } from "@/hooks/useTransitionPreview";
import {
  BASS_SWAP_WIDTH_BEATS_OPTIONS,
  CROSSFADE_BIAS_MAX,
  CROSSFADE_BIAS_MIN,
  GAIN_DB_MAX,
  GAIN_DB_MIN,
  TRANSITION_BEATS_OPTIONS,
  TRANSITION_STYLE_OPTIONS,
  bassSwapOffsetBeats,
  validBassSwapRange,
  type BassSwapWidthBeats,
  type TransitionBeats,
  type TransitionPlan,
  type TransitionStyle,
} from "@/lib/transitionPlan";
import type { PitchClass, TempoCompatibility } from "@/lib/api";

const TEMPO_COMPATIBILITY_LABEL: Record<TempoCompatibility, string> = {
  compatible: "great tempo match",
  moderate: "good tempo match",
  significant: "noticeable tempo adjustment",
  extreme: "large tempo mismatch — results may sound off",
};

type HarmonicMatchLabel =
  | "highly compatible"
  | "compatible"
  | "mixed"
  | "tense"
  | "unknown";

/**
 * Maps the numeric harmonic-compatibility score to a restrained,
 * documented label. "unknown" whenever either side's local key couldn't
 * be trusted — the score itself falls back to a neutral 0.5 in that case,
 * which must never be presented as if it were an actual measurement.
 *
 * Thresholds (score is always in [0, 1]):
 *   >= 0.85            -> "highly compatible"  (same/relative key, or better)
 *   >= 0.65             -> "compatible"         (fifth/fourth, parallel major-minor)
 *   >= 0.4              -> "mixed"
 *   <  0.4              -> "tense"
 */
function harmonicMatchLabel(
  compatibility: number,
  songALocalKey: PitchClass | null,
  songBLocalKey: PitchClass | null,
): HarmonicMatchLabel {
  if (songALocalKey === null || songBLocalKey === null) return "unknown";
  if (compatibility >= 0.85) return "highly compatible";
  if (compatibility >= 0.65) return "compatible";
  if (compatibility >= 0.4) return "mixed";
  return "tense";
}

interface TransitionMixerProps {
  plan: TransitionPlan;
  suggestionInfo: SuggestionInfo | null;
  onTransitionBeatsChange: (beats: TransitionBeats) => void;
  onSongAGainChange: (db: number) => void;
  onSongBGainChange: (db: number) => void;
  onCrossfadeBiasChange: (bias: number) => void;
  onTransitionStyleChange: (style: TransitionStyle) => void;
  onBassSwapPositionChange: (position: number) => void;
  onBassSwapWidthChange: (width: BassSwapWidthBeats) => void;
  onResetMixSettings: () => void;
  onGenerate: () => void;
  previewStatus: TransitionPreviewState["status"];
  /** True only for a successful preview that matches the current plan. */
  hasFreshPreview: boolean;
  isMixAtDefaults: boolean;
}

/**
 * The editor's inspector: status, then every editable mix control, then
 * the generate action. Anchors live on the decks. Once a fresh preview
 * exists, Export (in the preview panel) becomes the dominant action and
 * this one steps back to secondary, so only one action leads at a time.
 */
export function TransitionMixer({
  plan,
  suggestionInfo,
  onTransitionBeatsChange,
  onSongAGainChange,
  onSongBGainChange,
  onCrossfadeBiasChange,
  onTransitionStyleChange,
  onBassSwapPositionChange,
  onBassSwapWidthChange,
  onResetMixSettings,
  onGenerate,
  previewStatus,
  hasFreshPreview,
  isMixAtDefaults,
}: TransitionMixerProps) {
  const isGenerating = previewStatus === "generating";
  const hasPreview = previewStatus === "success";
  const generateLabel = isGenerating
    ? "Generating transition…"
    : hasPreview
      ? "Regenerate preview"
      : "Generate preview";
  const [bassMin, bassMax] = validBassSwapRange(plan.transitionBeats, plan.bassSwapWidthBeats);
  const bassOffsetBeats = bassSwapOffsetBeats(plan.bassSwapPosition, plan.transitionBeats);

  return (
    <section
      aria-labelledby="mixer-heading"
      className="flex flex-col gap-5 rounded-2xl bg-ed-surface p-4 sm:p-5"
    >
      <h2 id="mixer-heading" className="text-sm font-semibold text-ed-strong">
        Mixer
      </h2>

      <StatusBlock info={suggestionInfo} />

      <div className="grid gap-x-8 gap-y-5 md:grid-cols-2 xl:grid-cols-1">
        <div className="flex flex-col gap-5">
          <SegmentedField
            label="Length"
            suffix="beats"
            options={TRANSITION_BEATS_OPTIONS}
            value={plan.transitionBeats}
            onChange={onTransitionBeatsChange}
            render={(beats) => String(beats)}
          />
          <SegmentedField
            label="Transition style"
            options={TRANSITION_STYLE_OPTIONS}
            value={plan.transitionStyle}
            onChange={onTransitionStyleChange}
            render={(style) => (style === "smooth" ? "Smooth" : "Bass swap")}
          />
          {plan.transitionStyle === "bass_swap" && (
            <>
              <RangeField
                label="Bass swap timing"
                valueText={formatBassSwapOffset(bassOffsetBeats)}
                min={bassMin}
                max={bassMax}
                step={0.01}
                value={plan.bassSwapPosition}
                onChange={onBassSwapPositionChange}
                origin="center"
                endLabels={["Earlier", "Later"]}
              />
              <SegmentedField
                label="Bass swap width"
                options={BASS_SWAP_WIDTH_BEATS_OPTIONS}
                value={plan.bassSwapWidthBeats}
                onChange={onBassSwapWidthChange}
                render={(width) => `${width} beats`}
              />
            </>
          )}
        </div>

        <div className="flex flex-col gap-5">
          <RangeField
            label="Song A level"
            valueText={formatDb(plan.songAGainDb)}
            min={GAIN_DB_MIN}
            max={GAIN_DB_MAX}
            step={0.5}
            value={plan.songAGainDb}
            onChange={onSongAGainChange}
            tone="var(--ed-violet)"
            dotClass="bg-ed-violet"
            onReset={() => onSongAGainChange(0)}
            isDefault={plan.songAGainDb === 0}
          />
          <RangeField
            label="Song B level"
            valueText={formatDb(plan.songBGainDb)}
            min={GAIN_DB_MIN}
            max={GAIN_DB_MAX}
            step={0.5}
            value={plan.songBGainDb}
            onChange={onSongBGainChange}
            tone="var(--ed-teal)"
            dotClass="bg-ed-teal"
            onReset={() => onSongBGainChange(0)}
            isDefault={plan.songBGainDb === 0}
          />
          <RangeField
            label="Blend timing"
            min={CROSSFADE_BIAS_MIN}
            max={CROSSFADE_BIAS_MAX}
            step={0.05}
            value={plan.crossfadeBias}
            onChange={onCrossfadeBiasChange}
            origin="center"
            endLabels={["Early B", "Late B"]}
            onReset={() => onCrossfadeBiasChange(0)}
            isDefault={plan.crossfadeBias === 0}
          />
        </div>
      </div>

      <div className="flex flex-col items-stretch gap-3 xl:sticky xl:bottom-0 xl:-mx-5 xl:-mb-5 xl:bg-ed-surface xl:px-5 xl:pb-5 xl:pt-3">
        <button
          type="button"
          onClick={onResetMixSettings}
          disabled={isMixAtDefaults}
          className="ed-btn-ghost -ml-2 self-start"
        >
          Reset mix settings
        </button>
        <button
          type="button"
          onClick={onGenerate}
          disabled={isGenerating}
          aria-busy={isGenerating}
          className={`ed-btn min-h-11 w-full ${hasFreshPreview ? "ed-btn-secondary" : "ed-btn-primary"}`}
        >
          {generateLabel}
        </button>
      </div>
    </section>
  );
}

function StatusBlock({ info }: { info: SuggestionInfo | null }) {
  return (
    <div aria-live="polite" className="rounded-xl bg-ed-raised p-3.5">
      {info ? (
        <>
          <p className="text-[13px] font-semibold text-ed-strong">
            {info.isEdited ? "Edited suggestion" : "Suggested starting point"}
          </p>
          <dl className="mt-2.5 grid gap-1.5 text-[13px]">
            <StatusRow label="Tempo" value={TEMPO_COMPATIBILITY_LABEL[info.tempoCompatibility]} />
            {info.usedTempoNormalization && (
              <StatusRow
                label="Tempo interpretation"
                mono
                value={`${info.songBRawBpm.toFixed(1)} → ${info.effectiveSongBBpm.toFixed(1)} BPM`}
              />
            )}
            <StatusRow
              label="Harmonic match"
              value={harmonicMatchLabel(
                info.harmonicCompatibility,
                info.songALocalKey,
                info.songBLocalKey,
              )}
            />
            {info.songALocalKey &&
              info.songALocalMode &&
              info.songBLocalKey &&
              info.songBLocalMode && (
                <StatusRow
                  label="Local harmony"
                  value={`${info.songALocalKey} ${info.songALocalMode} → ${info.songBLocalKey} ${info.songBLocalMode}`}
                />
              )}
          </dl>
        </>
      ) : (
        <>
          <p className="text-[13px] font-semibold text-ed-strong">Manual transition</p>
          <p className="mt-1 text-[13px] text-ed-muted">Anchors selected by hand.</p>
        </>
      )}
    </div>
  );
}

function StatusRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="shrink-0 text-ed-muted">{label}</dt>
      <dd className={`text-right text-ed-text ${mono ? "font-mono tabular-nums" : ""}`}>{value}</dd>
    </div>
  );
}

function formatDb(db: number): string {
  return `${db > 0 ? "+" : ""}${db.toFixed(1)} dB`;
}

/** Formats a bass-swap offset as a restrained, human-readable label —
 * never the raw normalized position (e.g. "0.537"). */
function formatBassSwapOffset(offsetBeats: number): string {
  if (Math.abs(offsetBeats) < 0.05) return "At anchor";
  const rounded = Math.round(Math.abs(offsetBeats) * 10) / 10;
  const magnitude = rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1);
  return offsetBeats < 0 ? `${magnitude} beats early` : `${magnitude} beats late`;
}

function FieldLabel({ children, id }: { children: ReactNode; id: string }) {
  return (
    <span id={id} className="text-[13px] font-medium text-ed-muted">
      {children}
    </span>
  );
}

/** A tonal segmented toggle. Active state is drawn from aria-pressed (see
 * .ed-seg in globals.css): tonal fill, brighter text, heavier weight and a
 * ring, so it never rides on color alone. */
function SegmentedField<T extends string | number>({
  label,
  suffix,
  options,
  value,
  onChange,
  render,
}: {
  label: string;
  suffix?: string;
  options: readonly T[];
  value: T;
  onChange: (value: T) => void;
  render: (option: T) => string;
}) {
  const labelId = useId();
  return (
    <div role="group" aria-labelledby={labelId} className="flex flex-col gap-2">
      <FieldLabel id={labelId}>{label}</FieldLabel>
      <div className="flex flex-wrap items-center gap-3">
        <div className="ed-seg">
          {options.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onChange(option)}
              aria-pressed={value === option}
            >
              {render(option)}
            </button>
          ))}
        </div>
        {suffix && <span className="text-xs text-ed-muted">{suffix}</span>}
      </div>
    </div>
  );
}

const THUMB_PX = 20;

/** Where the native thumb's center sits for a value at `percent` of the
 * range — the thumb travels the track minus its own width, so the fill has
 * to be offset to end under it. */
function thumbStop(percent: number): string {
  return `calc(${percent}% + ${((0.5 - percent / 100) * THUMB_PX).toFixed(2)}px)`;
}

/**
 * A native range input with a label, a mono readout and optional Reset.
 * Behavior is the browser's own (keyboard, screen readers); only the
 * paint changes. `origin="center"` fills outward from the midpoint, for
 * controls that are balanced around a neutral value.
 */
function RangeField({
  label,
  valueText,
  min,
  max,
  step,
  value,
  onChange,
  tone = "var(--ed-strong)",
  dotClass,
  origin = "start",
  endLabels,
  onReset,
  isDefault = false,
}: {
  label: string;
  valueText?: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (value: number) => void;
  tone?: string;
  dotClass?: string;
  origin?: "start" | "center";
  endLabels?: [string, string];
  onReset?: () => void;
  /** With onReset: true while the value already equals its default. */
  isDefault?: boolean;
}) {
  const id = useId();
  const percent = max === min ? 0 : ((value - min) / (max - min)) * 100;
  const lo = origin === "center" ? Math.min(50, percent) : 0;
  const hi = origin === "center" ? Math.max(50, percent) : percent;

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className="flex items-center gap-2 text-[13px] font-medium text-ed-muted">
          {dotClass && <span aria-hidden="true" className={`size-2 rounded-full ${dotClass}`} />}
          {label}
        </label>
        <div className={`flex items-center gap-1 ${onReset ? "-mr-2" : ""}`}>
          {valueText && (
            <output
              htmlFor={id}
              className="font-mono text-[13px] tabular-nums text-ed-strong"
            >
              {valueText}
            </output>
          )}
          {onReset && (
            // Always laid out so the readout doesn't shift when a value
            // leaves its default; hidden (and unfocusable) while at default.
            <button
              type="button"
              onClick={onReset}
              disabled={isDefault}
              aria-label={`Reset ${label.toLowerCase()}`}
              className={`ed-btn-ghost ${isDefault ? "invisible" : ""}`}
            >
              Reset
            </button>
          )}
        </div>
      </div>
      <input
        id={id}
        type="range"
        className="ed-range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-valuetext={valueText}
        onChange={(event) => onChange(Number(event.target.value))}
        style={
          {
            "--tone": tone,
            "--lo": thumbStop(lo),
            "--hi": thumbStop(hi),
          } as CSSProperties
        }
      />
      {endLabels && (
        <div aria-hidden="true" className="flex justify-between text-xs text-ed-muted">
          <span>{endLabels[0]}</span>
          <span>{endLabels[1]}</span>
        </div>
      )}
    </div>
  );
}
