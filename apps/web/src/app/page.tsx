"use client";

import { useState } from "react";
import { BackendStatus } from "@/components/BackendStatus";
import { TrackSlot } from "@/components/TrackSlot";
import { TransitionAnchorSummary } from "@/components/TransitionAnchorSummary";
import type { BeatAnchor } from "@/lib/transitionPlan";

export default function Home() {
  // Shared transition state: the eventual TransitionPlan for this session.
  // Lives here (the nearest common ancestor of both track slots) since the
  // alignment summary below needs both anchors at once.
  const [songAAnchor, setSongAAnchor] = useState<BeatAnchor | null>(null);
  const [songBAnchor, setSongBAnchor] = useState<BeatAnchor | null>(null);

  return (
    <div className="flex flex-1 flex-col bg-white dark:bg-black">
      <header className="flex items-start justify-between gap-4 px-8 py-8 sm:px-12">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Song Transition Studio
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Load two tracks to start building a transition.
          </p>
        </div>
        <div className="origin-top-right scale-90 opacity-60">
          <BackendStatus />
        </div>
      </header>

      <main className="flex flex-1 flex-col gap-12 px-8 pb-20 sm:px-12">
        <TrackSlot
          label="Song A"
          accent="violet"
          anchor={songAAnchor}
          onAnchorChange={setSongAAnchor}
        />
        <TrackSlot
          label="Song B"
          accent="teal"
          anchor={songBAnchor}
          onAnchorChange={setSongBAnchor}
        />

        <TransitionAnchorSummary
          songAAnchor={songAAnchor}
          songBAnchor={songBAnchor}
        />
      </main>
    </div>
  );
}
