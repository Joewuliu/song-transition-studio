"use client";

import type { SuggestionInfo } from "@/context/StudioContext";
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
  isGenerating: boolean;
  isMixAtDefaults: boolean;
}

/**
 * The center column of the DJ workstation: every editable TransitionPlan
 * control except the anchors themselves (Deck A/Deck B own those). Pure
 * presentation over the shared workspace state — see StudioContext.
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
  isGenerating,
  isMixAtDefaults,
}: TransitionMixerProps) {
  return (
    <section className="flex flex-col gap-6 rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-black">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
        Mixer
      </h2>

      {/* Top: transition status — always present, so the mixer never
          opens with an empty header regardless of how the plan got here. */}
      {suggestionInfo ? (
        <div
          aria-live="polite"
          className="flex flex-col gap-1 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400"
        >
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
          <span>
            Harmonic match:{" "}
            {harmonicMatchLabel(
              suggestionInfo.harmonicCompatibility,
              suggestionInfo.songALocalKey,
              suggestionInfo.songBLocalKey,
            )}
          </span>
          {suggestionInfo.songALocalKey &&
            suggestionInfo.songALocalMode &&
            suggestionInfo.songBLocalKey &&
            suggestionInfo.songBLocalMode && (
              <span>
                Local harmony: {suggestionInfo.songALocalKey}{" "}
                {suggestionInfo.songALocalMode} → {suggestionInfo.songBLocalKey}{" "}
                {suggestionInfo.songBLocalMode}
              </span>
            )}
        </div>
      ) : (
        <div className="rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
          <span className="font-medium text-zinc-700 dark:text-zinc-300">
            Manual transition
          </span>{" "}
          — anchors selected by hand.
        </div>
      )}

      {/* Middle: every editable mix control. */}
      <div className="flex flex-col gap-6 border-t border-zinc-100 pt-6 dark:border-zinc-800">
        <LengthSelector value={plan.transitionBeats} onChange={onTransitionBeatsChange} />

        <TransitionStyleSelector
          value={plan.transitionStyle}
          onChange={onTransitionStyleChange}
        />

        {plan.transitionStyle === "bass_swap" && (
          <>
            <BassSwapTimingSlider
              position={plan.bassSwapPosition}
              transitionBeats={plan.transitionBeats}
              bassSwapWidthBeats={plan.bassSwapWidthBeats}
              onChange={onBassSwapPositionChange}
            />
            <BassSwapWidthSelector
              value={plan.bassSwapWidthBeats}
              onChange={onBassSwapWidthChange}
            />
          </>
        )}

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
      </div>

      {/* Bottom: reset and generate/regenerate. */}
      <div className="flex flex-wrap items-center gap-4 border-t border-zinc-100 pt-6 dark:border-zinc-800">
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

const TRANSITION_STYLE_LABEL: Record<TransitionStyle, string> = {
  smooth: "Smooth",
  bass_swap: "Bass swap",
};

function TransitionStyleSelector({
  value,
  onChange,
}: {
  value: TransitionStyle;
  onChange: (style: TransitionStyle) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-zinc-600 dark:text-zinc-400">
        Transition style
      </span>
      <div className="inline-flex w-fit rounded-full border border-zinc-300 p-0.5 dark:border-zinc-700">
        {TRANSITION_STYLE_OPTIONS.map((style) => (
          <button
            key={style}
            type="button"
            onClick={() => onChange(style)}
            aria-pressed={value === style}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              value === style
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            }`}
          >
            {TRANSITION_STYLE_LABEL[style]}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Formats a bass-swap offset as a restrained, human-readable label —
 * never the raw normalized position (e.g. "0.537"). */
function formatBassSwapOffset(offsetBeats: number): string {
  if (Math.abs(offsetBeats) < 0.05) return "At anchor";
  const rounded = Math.round(Math.abs(offsetBeats) * 10) / 10;
  const magnitude = rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(1);
  return offsetBeats < 0 ? `${magnitude} beats early` : `${magnitude} beats late`;
}

function BassSwapTimingSlider({
  position,
  transitionBeats,
  bassSwapWidthBeats,
  onChange,
}: {
  position: number;
  transitionBeats: TransitionBeats;
  bassSwapWidthBeats: BassSwapWidthBeats;
  onChange: (position: number) => void;
}) {
  const [min, max] = validBassSwapRange(transitionBeats, bassSwapWidthBeats);
  const offsetBeats = bassSwapOffsetBeats(position, transitionBeats);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs text-zinc-600 dark:text-zinc-400">
        <span>Bass swap timing</span>
        <span className="tabular-nums">{formatBassSwapOffset(offsetBeats)}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-400">
          Earlier
        </span>
        <input
          type="range"
          min={min}
          max={max}
          step={0.01}
          value={position}
          onChange={(event) => onChange(Number(event.target.value))}
          aria-label="Bass swap timing"
          className="w-full accent-zinc-700 dark:accent-zinc-300"
        />
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-zinc-400">
          Later
        </span>
      </div>
    </div>
  );
}

function BassSwapWidthSelector({
  value,
  onChange,
}: {
  value: BassSwapWidthBeats;
  onChange: (width: BassSwapWidthBeats) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-zinc-600 dark:text-zinc-400">Bass swap width</span>
      <div className="inline-flex w-fit rounded-full border border-zinc-300 p-0.5 dark:border-zinc-700">
        {BASS_SWAP_WIDTH_BEATS_OPTIONS.map((width) => (
          <button
            key={width}
            type="button"
            onClick={() => onChange(width)}
            aria-pressed={value === width}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              value === width
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            }`}
          >
            {width} beats
          </button>
        ))}
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
