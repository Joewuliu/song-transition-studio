import type { TransitionPlan } from "@/lib/transitionPlan";

interface TransitionCurveVisualizationProps {
  plan: Pick<TransitionPlan, "crossfadeBias" | "songAGainDb" | "songBGainDb">;
}

const SAMPLE_COUNT = 80;
const VIEW_WIDTH = 320;
const VIEW_HEIGHT = 120;
const PADDING_X = 10;
const PADDING_Y = 10;

const SONG_A_COLOR = "#8b5cf6";
const SONG_B_COLOR = "#14b8a6";

/**
 * A purely explanatory curve — it derives directly from the current plan
 * (crossfadeBias reshapes *when* each song dominates; gain trims scale the
 * displayed curve heights) but is not a sample-level audio waveform.
 */
export function TransitionCurveVisualization({
  plan,
}: TransitionCurveVisualizationProps) {
  const gamma = 2 ** plan.crossfadeBias;
  const linearGainA = 10 ** (plan.songAGainDb / 20);
  const linearGainB = 10 ** (plan.songBGainDb / 20);

  const gainsA: number[] = [];
  const gainsB: number[] = [];
  for (let i = 0; i <= SAMPLE_COUNT; i++) {
    const x = i / SAMPLE_COUNT;
    const biasedX = Math.pow(x, gamma);
    gainsA.push(Math.cos((biasedX * Math.PI) / 2) * linearGainA);
    gainsB.push(Math.sin((biasedX * Math.PI) / 2) * linearGainB);
  }

  const maxY = Math.max(1, ...gainsA, ...gainsB) * 1.05;
  const plotWidth = VIEW_WIDTH - PADDING_X * 2;
  const plotHeight = VIEW_HEIGHT - PADDING_Y * 2;

  const toPath = (values: number[]) =>
    values
      .map((value, index) => {
        const x = PADDING_X + (index / SAMPLE_COUNT) * plotWidth;
        const y = PADDING_Y + plotHeight - (value / maxY) * plotHeight;
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  const midX = PADDING_X + 0.5 * plotWidth;

  return (
    <div className="flex flex-col gap-2">
      <svg
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        className="w-full"
        role="img"
        aria-label="Song A and Song B gain curves across the transition, with the aligned anchor at the midpoint"
      >
        <line
          x1={midX}
          y1={PADDING_Y}
          x2={midX}
          y2={VIEW_HEIGHT - PADDING_Y}
          className="stroke-zinc-300 dark:stroke-zinc-700"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        <path d={toPath(gainsA)} fill="none" stroke={SONG_A_COLOR} strokeWidth={2} />
        <path d={toPath(gainsB)} fill="none" stroke={SONG_B_COLOR} strokeWidth={2} />

        <text
          x={PADDING_X}
          y={VIEW_HEIGHT - 2}
          fontSize={9}
          className="fill-zinc-400 dark:fill-zinc-500"
        >
          start
        </text>
        <text
          x={midX}
          y={PADDING_Y - 1}
          fontSize={9}
          textAnchor="middle"
          className="fill-zinc-400 dark:fill-zinc-500"
        >
          anchors align
        </text>
        <text
          x={VIEW_WIDTH - PADDING_X}
          y={VIEW_HEIGHT - 2}
          fontSize={9}
          textAnchor="end"
          className="fill-zinc-400 dark:fill-zinc-500"
        >
          end
        </text>
      </svg>

      <div className="flex items-center gap-4 text-xs text-zinc-500 dark:text-zinc-400">
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: SONG_A_COLOR }}
          />
          Song A
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: SONG_B_COLOR }}
          />
          Song B
        </span>
      </div>
    </div>
  );
}
