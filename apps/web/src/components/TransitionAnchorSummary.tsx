import { formatTimestamp } from "@/lib/audio";
import { toDisplayBeatNumber } from "@/lib/beats";
import { ACCENT_STYLES } from "@/lib/trackAccent";
import type { TransitionPlan } from "@/lib/transitionPlan";

interface TransitionAnchorSummaryProps {
  plan: TransitionPlan;
}

export function TransitionAnchorSummary({ plan }: TransitionAnchorSummaryProps) {
  const { songAAnchor, songBAnchor } = plan;
  if (!songAAnchor || !songBAnchor) return null;

  const offsetSeconds = songBAnchor.timeSeconds - songAAnchor.timeSeconds;
  const offsetLabel = `${offsetSeconds >= 0 ? "+" : "-"}${formatTimestamp(
    Math.abs(offsetSeconds),
  )}`;

  return (
    <section className="flex flex-col gap-4 border-t border-zinc-200 pt-6 dark:border-zinc-800">
      <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Transition anchors
      </h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <span className={`text-xs font-medium ${ACCENT_STYLES.violet.text}`}>
            Song A
          </span>
          <span className="text-sm text-zinc-700 dark:text-zinc-300">
            Beat {toDisplayBeatNumber(songAAnchor.beatIndex)} ·{" "}
            {formatTimestamp(songAAnchor.timeSeconds)}
          </span>
        </div>
        <div className="flex flex-col gap-1">
          <span className={`text-xs font-medium ${ACCENT_STYLES.teal.text}`}>
            Song B
          </span>
          <span className="text-sm text-zinc-700 dark:text-zinc-300">
            Beat {toDisplayBeatNumber(songBAnchor.beatIndex)} ·{" "}
            {formatTimestamp(songBAnchor.timeSeconds)}
          </span>
        </div>
      </div>

      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Raw anchor offset: {offsetLabel} (Song B anchor relative to Song A).
        This only records which beats will eventually be aligned — it does
        not account for tempo matching or ongoing synchronization.
      </p>
    </section>
  );
}
