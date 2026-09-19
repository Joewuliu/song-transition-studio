"use client";

import { useEffect, useRef, useState } from "react";
import type { TransitionPlan } from "@/lib/transitionPlan";

interface TransitionCurveVisualizationProps {
  plan: Pick<
    TransitionPlan,
    | "crossfadeBias"
    | "songAGainDb"
    | "songBGainDb"
    | "transitionStyle"
    | "bassSwapPosition"
    | "bassSwapWidthBeats"
    | "transitionBeats"
  >;
}

const SAMPLE_COUNT = 80;
const PADDING_X = 14;
// Right gutter holds the "0 dB" reference label so it never sits on a curve.
const PADDING_RIGHT = 46;
const PADDING_TOP = 30;
const PADDING_BOTTOM = 30;
const DEFAULT_WIDTH = 720;

const SONG_A_COLOR = "var(--ed-violet)";
const SONG_B_COLOR = "var(--ed-teal)";

/**
 * A purely explanatory curve — it derives directly from the current plan
 * (crossfadeBias reshapes *when* each song dominates; gain trims scale the
 * displayed curve heights; for Bass Swap, the same formulas the renderer
 * uses for bass_swap_gains are drawn as a second, narrower pair of
 * dashed curves) but is not a sample-level audio waveform.
 *
 * The SVG is drawn in real pixels (its viewBox tracks the measured width)
 * so labels keep a constant, readable size from phone to desktop instead
 * of shrinking with the diagram.
 */
export function TransitionCurveVisualization({
  plan,
}: TransitionCurveVisualizationProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(DEFAULT_WIDTH);

  useEffect(() => {
    const element = wrapperRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => {
      const measured = Math.round(entries[0].contentRect.width);
      if (measured > 0) setWidth(measured);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const height = width < 520 ? 210 : 260;

  const gamma = 2 ** plan.crossfadeBias;
  const linearGainA = 10 ** (plan.songAGainDb / 20);
  const linearGainB = 10 ** (plan.songBGainDb / 20);
  const isBassSwap = plan.transitionStyle === "bass_swap";

  const halfWidth = plan.bassSwapWidthBeats / (2 * plan.transitionBeats);
  const swapStart = plan.bassSwapPosition - halfWidth;
  const swapEnd = plan.bassSwapPosition + halfWidth;

  const gainsA: number[] = [];
  const gainsB: number[] = [];
  const bassGainsA: number[] = [];
  const bassGainsB: number[] = [];
  for (let i = 0; i <= SAMPLE_COUNT; i++) {
    const x = i / SAMPLE_COUNT;
    const biasedX = Math.pow(x, gamma);
    gainsA.push(Math.cos((biasedX * Math.PI) / 2) * linearGainA);
    gainsB.push(Math.sin((biasedX * Math.PI) / 2) * linearGainB);

    if (isBassSwap) {
      const bassT = Math.min(Math.max((x - swapStart) / (swapEnd - swapStart), 0), 1);
      bassGainsA.push(Math.cos((bassT * Math.PI) / 2) * linearGainA);
      bassGainsB.push(Math.sin((bassT * Math.PI) / 2) * linearGainB);
    }
  }

  const maxY = Math.max(1, ...gainsA, ...gainsB) * 1.05;
  const plotRight = width - PADDING_RIGHT;
  const plotWidth = plotRight - PADDING_X;
  const plotHeight = height - PADDING_TOP - PADDING_BOTTOM;

  const xAt = (fraction: number) => PADDING_X + fraction * plotWidth;
  const yAt = (value: number) => PADDING_TOP + plotHeight - (value / maxY) * plotHeight;

  const toPath = (values: number[]) =>
    values
      .map((value, index) => {
        const x = xAt(index / SAMPLE_COUNT);
        const y = yAt(value);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  const anchorX = xAt(0.5);
  const unityY = yAt(1);
  const baselineY = yAt(0);
  const bassBandStart = xAt(Math.max(swapStart, 0));
  const bassBandEnd = xAt(Math.min(swapEnd, 1));
  const bassCenterX = xAt(plan.bassSwapPosition);

  const description = isBassSwap
    ? "Song A and Song B gain curves across the transition, with the aligned anchor at the midpoint and a narrower bass-ownership swap drawn as dashed curves and a shaded band"
    : "Song A and Song B gain curves across the transition, with the aligned anchor at the midpoint";

  return (
    <div ref={wrapperRef} className="flex flex-col gap-3">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        className="block w-full"
        role="img"
        aria-label={description}
      >
        {isBassSwap && (
          <rect
            x={bassBandStart}
            y={PADDING_TOP}
            width={Math.max(bassBandEnd - bassBandStart, 0)}
            height={plotHeight}
            className="fill-white/5"
          />
        )}

        <line
          x1={PADDING_X}
          x2={plotRight}
          y1={unityY}
          y2={unityY}
          className="stroke-white/15"
          strokeDasharray="2 5"
        />
        <line
          x1={PADDING_X}
          x2={plotRight}
          y1={baselineY}
          y2={baselineY}
          className="stroke-white/20"
        />

        <line
          x1={anchorX}
          x2={anchorX}
          y1={PADDING_TOP - 8}
          y2={baselineY}
          className="stroke-ed-amber"
          strokeWidth={1.5}
          strokeDasharray="4 4"
        />

        {isBassSwap && Math.abs(plan.bassSwapPosition - 0.5) > 0.01 && (
          <line
            x1={bassCenterX}
            x2={bassCenterX}
            y1={PADDING_TOP}
            y2={baselineY}
            className="stroke-white/50"
            strokeWidth={1}
          />
        )}

        <path
          d={toPath(gainsA)}
          fill="none"
          stroke={SONG_A_COLOR}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={toPath(gainsB)}
          fill="none"
          stroke={SONG_B_COLOR}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {isBassSwap && (
          <>
            <path
              d={toPath(bassGainsA)}
              fill="none"
              stroke={SONG_A_COLOR}
              strokeWidth={2}
              strokeDasharray="6 4"
              strokeLinecap="round"
              opacity={0.85}
            />
            <path
              d={toPath(bassGainsB)}
              fill="none"
              stroke={SONG_B_COLOR}
              strokeWidth={2}
              strokeDasharray="6 4"
              strokeLinecap="round"
              opacity={0.85}
            />
          </>
        )}

        <text
          x={PADDING_X + 6}
          y={yAt(gainsA[0]) + 22}
          fontSize={13}
          fontWeight={600}
          className="fill-ed-violet"
        >
          Song A
        </text>
        <text
          x={plotRight - 6}
          y={yAt(gainsB[SAMPLE_COUNT]) + 22}
          fontSize={13}
          fontWeight={600}
          textAnchor="end"
          className="fill-ed-teal"
        >
          Song B
        </text>

        <text
          x={anchorX}
          y={PADDING_TOP - 14}
          fontSize={12}
          textAnchor="middle"
          className="fill-ed-amber"
        >
          Anchors align
        </text>
        <text
          x={PADDING_X}
          y={height - 8}
          fontSize={12}
          className="fill-ed-muted"
        >
          Start
        </text>
        <text
          x={plotRight}
          y={height - 8}
          fontSize={12}
          textAnchor="end"
          className="fill-ed-muted"
        >
          End
        </text>
        {isBassSwap && (
          <text
            x={(bassBandStart + bassBandEnd) / 2}
            y={height - 8}
            fontSize={12}
            textAnchor="middle"
            className="fill-ed-muted"
          >
            Bass swap
          </text>
        )}
        <text
          x={width - 4}
          y={unityY + 4}
          fontSize={12}
          textAnchor="end"
          className="fill-ed-faint"
        >
          0 dB
        </text>
      </svg>

      {isBassSwap && (
        <p className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-ed-muted">
          <span className="flex items-center gap-2">
            <svg width="22" height="6" aria-hidden="true">
              <line x1="0" x2="22" y1="3" y2="3" stroke="currentColor" strokeWidth="2.5" />
            </svg>
            Overall blend
          </span>
          <span className="flex items-center gap-2">
            <svg width="22" height="6" aria-hidden="true">
              <line
                x1="0"
                x2="22"
                y1="3"
                y2="3"
                stroke="currentColor"
                strokeWidth="2"
                strokeDasharray="5 3"
              />
            </svg>
            Bass only
          </span>
        </p>
      )}
    </div>
  );
}
