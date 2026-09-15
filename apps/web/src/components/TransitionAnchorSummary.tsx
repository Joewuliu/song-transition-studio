import { formatTimestamp } from "@/lib/audio";
import { ACCENT_STYLES } from "@/lib/trackAccent";
import type { BeatAnchor } from "@/lib/transitionPlan";

interface TransitionAnchorSummaryProps {
  songAAnchor: BeatAnchor | null;
  songBAnchor: BeatAnchor | null;
}

export function TransitionAnchorSummary({
  songAAnchor,
  songBAnchor,
}: TransitionAnchorSummaryProps) {
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
            Beat {songAAnchor.beatIndex} · {formatTimestamp(songAAnchor.timeSeconds)}
          </span>
        </div>
        <div className="flex flex-col gap-1">
          <span className={`text-xs font-medium ${ACCENT_STYLES.teal.text}`}>
            Song B
          </span>
          <span className="text-sm text-zinc-700 dark:text-zinc-300">
            Beat {songBAnchor.beatIndex} · {formatTimestamp(songBAnchor.timeSeconds)}
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
