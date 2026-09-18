"use client";

import Link from "next/link";
import { BackendStatus } from "@/components/BackendStatus";
import { TrackSlot } from "@/components/TrackSlot";
import { TransitionOptionsPanel } from "@/components/TransitionOptionsPanel";
import { WorkflowProgress } from "@/components/WorkflowProgress";
import { useStudio } from "@/context/StudioContext";

/**
 * Track setup, analysis, and transition discovery. Detailed editing
 * lives on /editor — this page's job is getting to a valid
 * TransitionPlan (via an adopted variant or manual anchor selection),
 * then handing off.
 */
export default function StudioSetupPage() {
  const {
    songAFile,
    songBFile,
    songAAnalysis,
    songBAnalysis,
    transitionPlan,
    onSongAFileChange,
    onSongAAnalysisChange,
    onSongAAnchorChange,
    onSongBFileChange,
    onSongBAnalysisChange,
    onSongBAnchorChange,
    canSuggest,
    canGenerate,
    isPreviewFreshAndExportable,
    suggestionState,
    onFindTransitions,
    variantPreviewState,
    onPreviewVariant,
    onUseInEditor,
  } = useStudio();

  return (
    <div className="flex flex-1 flex-col bg-white dark:bg-black">
      <header className="flex flex-col gap-4 px-8 py-8 sm:px-12">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Song Transition Studio
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Add two local audio tracks to get started. Files stay on your
              device until you analyze or preview them.
            </p>
          </div>
          <div className="origin-top-right scale-90 opacity-60">
            <BackendStatus />
          </div>
        </div>
        <WorkflowProgress
          tracksAdded={songAFile !== null && songBFile !== null}
          bothAnalyzed={songAAnalysis !== null && songBAnalysis !== null}
          transitionChosen={canGenerate}
          exportReady={isPreviewFreshAndExportable}
        />
      </header>

      <main className="flex flex-1 flex-col gap-12 px-8 pb-20 sm:px-12">
        <TrackSlot
          label="Song A"
          accent="violet"
          file={songAFile}
          onFileChange={onSongAFileChange}
          onAnalysisChange={onSongAAnalysisChange}
          anchor={transitionPlan.songAAnchor}
          onAnchorChange={onSongAAnchorChange}
        />
        <TrackSlot
          label="Song B"
          accent="teal"
          file={songBFile}
          onFileChange={onSongBFileChange}
          onAnalysisChange={onSongBAnalysisChange}
          anchor={transitionPlan.songBAnchor}
          onAnchorChange={onSongBAnchorChange}
        />
        {(songAFile === null) !== (songBFile === null) && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Add {songAFile === null ? "Song A" : "Song B"} to continue.
          </p>
        )}

        {canSuggest && (
          <TransitionOptionsPanel
            suggestionState={suggestionState}
            onFindTransitions={onFindTransitions}
            variantPreviewState={variantPreviewState}
            onPreviewVariant={onPreviewVariant}
            onUseInEditor={onUseInEditor}
          />
        )}

        {canGenerate && (
          <section className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Your transition plan is ready to fine-tune.
            </p>
            <Link
              href="/editor"
              className="rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              Open editor
            </Link>
          </section>
        )}
      </main>
    </div>
  );
}
