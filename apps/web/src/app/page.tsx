"use client";

import { useCallback, useState } from "react";
import { BackendStatus } from "@/components/BackendStatus";
import { TrackSlot } from "@/components/TrackSlot";
import { TransitionAnchorSummary } from "@/components/TransitionAnchorSummary";
import { TransitionPreviewPanel } from "@/components/TransitionPreviewPanel";
import { useTransitionPreview } from "@/hooks/useTransitionPreview";
import type { TrackAnalysis } from "@/lib/api";
import { TRANSITION_BEATS, type BeatAnchor, type TransitionPlan } from "@/lib/transitionPlan";

export default function Home() {
  // Shared transition state. This — plus each song's File and TrackAnalysis
  // below — lives here (the nearest common ancestor of both track slots)
  // because both the alignment summary and the transition renderer need
  // everything from both songs at once.
  const [songAFile, setSongAFile] = useState<File | null>(null);
  const [songAAnalysis, setSongAAnalysis] = useState<TrackAnalysis | null>(null);
  const [songAAnchor, setSongAAnchor] = useState<BeatAnchor | null>(null);

  const [songBFile, setSongBFile] = useState<File | null>(null);
  const [songBAnalysis, setSongBAnalysis] = useState<TrackAnalysis | null>(null);
  const [songBAnchor, setSongBAnchor] = useState<BeatAnchor | null>(null);

  const preview = useTransitionPreview();

  // Any change to a track's file, analysis, or anchor invalidates a
  // previously generated preview — it was rendered from inputs that no
  // longer hold. Wrapping each setter here (rather than reaching into
  // TrackSlot/LoadedTrack) keeps that invariant in one place.
  const handleSongAFileChange = useCallback(
    (file: File | null) => {
      setSongAFile(file);
      preview.reset();
    },
    [preview],
  );
  const handleSongAAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongAAnalysis(analysis);
      preview.reset();
    },
    [preview],
  );
  const handleSongAAnchorChange = useCallback(
    (anchor: BeatAnchor | null) => {
      setSongAAnchor(anchor);
      preview.reset();
    },
    [preview],
  );

  const handleSongBFileChange = useCallback(
    (file: File | null) => {
      setSongBFile(file);
      preview.reset();
    },
    [preview],
  );
  const handleSongBAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongBAnalysis(analysis);
      preview.reset();
    },
    [preview],
  );
  const handleSongBAnchorChange = useCallback(
    (anchor: BeatAnchor | null) => {
      setSongBAnchor(anchor);
      preview.reset();
    },
    [preview],
  );

  const transitionPlan: TransitionPlan = {
    songAAnchor,
    songBAnchor,
    transitionBeats: TRANSITION_BEATS,
  };

  const canGenerate =
    songAFile !== null &&
    songAAnalysis !== null &&
    songAAnchor !== null &&
    songBFile !== null &&
    songBAnalysis !== null &&
    songBAnchor !== null;

  const handleGenerate = () => {
    if (
      !canGenerate ||
      preview.state.status === "generating" ||
      !songAFile ||
      !songAAnalysis ||
      !songAAnchor ||
      !songBFile ||
      !songBAnalysis ||
      !songBAnchor
    ) {
      return;
    }

    preview.generate({
      songAFile,
      songBFile,
      songAAnalysis,
      songBAnalysis,
      songAAnchor,
      songBAnchor,
    });
  };

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
          file={songAFile}
          onFileChange={handleSongAFileChange}
          onAnalysisChange={handleSongAAnalysisChange}
          anchor={songAAnchor}
          onAnchorChange={handleSongAAnchorChange}
        />
        <TrackSlot
          label="Song B"
          accent="teal"
          file={songBFile}
          onFileChange={handleSongBFileChange}
          onAnalysisChange={handleSongBAnalysisChange}
          anchor={songBAnchor}
          onAnchorChange={handleSongBAnchorChange}
        />

        <TransitionAnchorSummary plan={transitionPlan} />

        {canGenerate && (
          <section className="flex flex-col gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={preview.state.status === "generating"}
              className="self-start rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              {preview.state.status === "generating"
                ? "Generating transition…"
                : "Generate transition"}
            </button>
          </section>
        )}

        <TransitionPreviewPanel state={preview.state} />
      </main>
    </div>
  );
}
