interface WorkflowProgressProps {
  /** Both source files loaded (not necessarily analyzed yet). */
  tracksAdded: boolean;
  /** Both tracks have a successful analysis. */
  bothAnalyzed: boolean;
  /** The plan has both anchors — reached via an adopted transition option
   * or manual waveform selection; either path counts. */
  transitionChosen: boolean;
  /** A fresh (non-stale) successful editor preview exists. */
  exportReady: boolean;
}

const STAGE_LABELS = [
  "Add tracks",
  "Analyze",
  "Choose transition",
  "Fine tune",
  "Export",
] as const;

/**
 * A compact, read-only progress strip. The current stage is derived
 * entirely from the four EXISTING booleans above — no stage-tracking
 * state of its own. Reaching each stage is a strict prerequisite of the
 * next (you can't have anchors without analyses, can't have a fresh
 * preview without anchors, ...), so counting how many of the four
 * booleans are true is exactly the index of the current stage:
 *
 *   0 true  -> "Add tracks" current    (rule 1)
 *   1 true  -> "Analyze" current       (rule 2)
 *   2 true  -> "Choose transition"     (rule 3)
 *   3 true  -> "Fine tune" current     (rule 4)
 *   4 true  -> "Export" current        (rule 5)
 *
 * This makes progress move backward from Export to Fine tune the instant
 * `exportReady` goes false (an edit staled the preview) and forward again
 * the instant a regenerate makes it true — with no extra bookkeeping,
 * and identically whether anchors came from an adopted variant or manual
 * waveform selection.
 */
export function WorkflowProgress({
  tracksAdded,
  bothAnalyzed,
  transitionChosen,
  exportReady,
}: WorkflowProgressProps) {
  const currentIndex = [tracksAdded, bothAnalyzed, transitionChosen, exportReady].filter(
    Boolean,
  ).length;

  return (
    <ol
      aria-label="Workflow progress"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
    >
      {STAGE_LABELS.map((label, index) => {
        const isCurrent = index === currentIndex;
        const isComplete = index < currentIndex;
        return (
          <li key={label} className="flex items-center gap-2">
            {index > 0 && (
              <span aria-hidden="true" className="text-zinc-300 dark:text-zinc-700">
                ›
              </span>
            )}
            <span className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  isComplete || isCurrent
                    ? "bg-zinc-900 dark:bg-zinc-100"
                    : "border border-zinc-300 dark:border-zinc-700"
                }`}
              />
              <span
                className={
                  isCurrent
                    ? "font-medium text-zinc-900 dark:text-zinc-100"
                    : isComplete
                      ? "text-zinc-500 dark:text-zinc-400"
                      : "text-zinc-400 dark:text-zinc-600"
                }
              >
                {label}
                {isCurrent && <span className="sr-only"> (current step)</span>}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
