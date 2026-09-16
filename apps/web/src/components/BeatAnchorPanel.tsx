import { formatTimestamp } from "@/lib/audio";
import { toDisplayBeatNumber } from "@/lib/beats";

interface BeatAnchorPanelProps {
  selectedIndex: number | null;
  selectedTime: number | null;
  canSelectPrevious: boolean;
  canSelectNext: boolean;
  onSelectPrevious: () => void;
  onSelectNext: () => void;
}

export function BeatAnchorPanel({
  selectedIndex,
  selectedTime,
  canSelectPrevious,
  canSelectNext,
  onSelectPrevious,
  onSelectNext,
}: BeatAnchorPanelProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onSelectPrevious}
          disabled={!canSelectPrevious}
          aria-label="Select previous beat"
          className="flex h-6 w-6 items-center justify-center rounded-full border border-zinc-300 text-sm leading-none text-zinc-600 transition-colors hover:border-zinc-400 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-300"
        >
          ‹
        </button>
        <button
          type="button"
          onClick={onSelectNext}
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
  );
}
