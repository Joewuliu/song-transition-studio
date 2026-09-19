import { formatTimestamp } from "@/lib/audio";
import { toDisplayBeatNumber } from "@/lib/beats";
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
    <div className="flex flex-col gap-2">
      <dl className="grid gap-x-8 gap-y-1.5 text-[13px] sm:grid-cols-3">
        <Row
          label="Song A anchor"
          dotClass="bg-ed-violet"
          value={`Beat ${toDisplayBeatNumber(songAAnchor.beatIndex)} · ${formatTimestamp(songAAnchor.timeSeconds)}`}
        />
        <Row
          label="Song B anchor"
          dotClass="bg-ed-teal"
          value={`Beat ${toDisplayBeatNumber(songBAnchor.beatIndex)} · ${formatTimestamp(songBAnchor.timeSeconds)}`}
        />
        <Row label="Anchor offset" value={offsetLabel} />
      </dl>
      <p className="text-xs text-ed-muted">
        Raw anchor offset: {offsetLabel} (Song B anchor relative to Song A). This only
        records which beats will eventually be aligned — it does not account for tempo
        matching or ongoing synchronization.
      </p>
    </div>
  );
}

function Row({
  label,
  value,
  dotClass,
}: {
  label: string;
  value: string;
  dotClass?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="flex items-center gap-2 text-xs text-ed-muted">
        {dotClass && <span aria-hidden="true" className={`size-2 rounded-full ${dotClass}`} />}
        {label}
      </dt>
      <dd className="font-mono tabular-nums text-ed-strong">{value}</dd>
    </div>
  );
}
