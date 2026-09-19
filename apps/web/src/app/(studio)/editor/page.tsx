"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Deck } from "@/components/Deck";
import { ArrowLeftIcon } from "@/components/icons";
import { TransitionAnchorSummary } from "@/components/TransitionAnchorSummary";
import { TransitionCurveVisualization } from "@/components/TransitionCurveVisualization";
import { TransitionMixer } from "@/components/TransitionMixer";
import { TransitionPreviewPanel } from "@/components/TransitionPreviewPanel";
import { useStudio } from "@/context/StudioContext";

/**
 * The transition workstation. A stage (Deck A and Deck B side by side,
 * the transition curve, then preview and export) sits beside a sticky
 * inspector of every mix control. Everything reads from and writes to
 * the same StudioContext the setup page uses — nothing is re-implemented,
 * only presented. Below the wide-desktop breakpoint the sections stack:
 * decks, inspector, transition, preview.
 */
export default function EditorPage() {
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
    onTransitionBeatsChange,
    onSongAGainChange,
    onSongBGainChange,
    onCrossfadeBiasChange,
    onTransitionStyleChange,
    onBassSwapPositionChange,
    onBassSwapWidthChange,
    onResetMixSettings,
    onGenerate,
    isMixAtDefaults,
    isPreviewFreshAndExportable,
    suggestionInfo,
    canGenerate,
    previewState,
    defaultFilename,
  } = useStudio();

  // The uploaded files are memory-only by design (see StudioContext), so
  // a refresh or a direct visit always lands here with nothing loaded —
  // and removing a track while already here needs the same recovery.
  // canGenerate alone can't distinguish *why* the workspace isn't ready
  // (it only means "both anchors exist"), so check the three
  // prerequisites in order and explain whichever one is actually missing
  // rather than showing one generic message for every case.
  const bothFilesLoaded = songAFile !== null && songBFile !== null;
  const bothAnalyzed = songAAnalysis !== null && songBAnalysis !== null;
  const bothAnchorsSet =
    transitionPlan.songAAnchor !== null && transitionPlan.songBAnchor !== null;

  if (!bothFilesLoaded) {
    return (
      <RecoveryNotice message="Your local tracks aren't loaded." linkLabel="Return to setup" />
    );
  }
  if (!bothAnalyzed) {
    return (
      <RecoveryNotice
        message="Analyze both tracks before opening the editor."
        linkLabel="Back to tracks"
      />
    );
  }
  if (!bothAnchorsSet) {
    return (
      <RecoveryNotice
        message="Choose a transition before opening the editor."
        detail="Find a transition on the setup page or select transition beats manually."
        linkLabel="Back to tracks"
      />
    );
  }
  // bothFilesLoaded && bothAnalyzed && bothAnchorsSet is exactly what
  // canGenerate already means — asserted here only to narrow the types
  // below (songAFile/songBFile as File, not File | null) without
  // duplicating that condition.
  if (!canGenerate || !songAFile || !songBFile) {
    return (
      <RecoveryNotice message="Your local tracks aren't loaded." linkLabel="Return to setup" />
    );
  }

  return (
    <div className="editor-theme flex flex-1 flex-col bg-ed-canvas font-sans text-ed-text">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-1 px-4 py-4 sm:px-6">
        <Link href="/" className="ed-btn-ghost -ml-2 text-[13px]">
          <ArrowLeftIcon className="size-4" />
          Back to tracks
        </Link>
        <h1 className="text-sm font-medium text-ed-muted">Transition editor</h1>
      </header>

      <main className="grid grid-cols-1 content-start gap-4 px-4 pb-16 sm:px-6 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,28%)] xl:gap-5">
        <div className="grid min-w-0 gap-4 md:grid-cols-2 xl:col-start-1 xl:row-start-1">
          <Deck
            deckLabel="Deck A"
            accent="violet"
            file={songAFile}
            analysis={songAAnalysis}
            onFileChange={onSongAFileChange}
            onAnalysisChange={onSongAAnalysisChange}
            anchor={transitionPlan.songAAnchor}
            onAnchorChange={onSongAAnchorChange}
          />
          <Deck
            deckLabel="Deck B"
            accent="teal"
            file={songBFile}
            analysis={songBAnalysis}
            onFileChange={onSongBFileChange}
            onAnalysisChange={onSongBAnalysisChange}
            anchor={transitionPlan.songBAnchor}
            onAnchorChange={onSongBAnchorChange}
          />
        </div>

        <div className="min-w-0 rounded-2xl xl:sticky xl:top-4 xl:col-start-2 xl:row-span-3 xl:row-start-1 xl:max-h-[calc(100dvh-2rem)] xl:scroll-pb-28 xl:self-start xl:overflow-y-auto xl:overscroll-contain">
          <TransitionMixer
            plan={transitionPlan}
            suggestionInfo={suggestionInfo}
            onTransitionBeatsChange={onTransitionBeatsChange}
            onSongAGainChange={onSongAGainChange}
            onSongBGainChange={onSongBGainChange}
            onCrossfadeBiasChange={onCrossfadeBiasChange}
            onTransitionStyleChange={onTransitionStyleChange}
            onBassSwapPositionChange={onBassSwapPositionChange}
            onBassSwapWidthChange={onBassSwapWidthChange}
            onResetMixSettings={onResetMixSettings}
            onGenerate={onGenerate}
            previewStatus={previewState.status}
            hasFreshPreview={isPreviewFreshAndExportable}
            isMixAtDefaults={isMixAtDefaults}
          />
        </div>

        <section
          aria-labelledby="transition-heading"
          className="flex min-w-0 flex-col gap-4 rounded-2xl bg-ed-surface p-4 sm:p-5 xl:col-start-1 xl:row-start-2"
        >
          <div>
            <h2 id="transition-heading" className="text-sm font-semibold text-ed-strong">
              Transition
            </h2>
            <p className="mt-1 text-[13px] text-ed-muted">
              Song A fades out as Song B fades in, aligned at the two anchors.
            </p>
          </div>
          <TransitionCurveVisualization plan={transitionPlan} />
          <TransitionAnchorSummary plan={transitionPlan} />
        </section>

        <div className="min-w-0 xl:col-start-1 xl:row-start-3">
          <TransitionPreviewPanel
            state={previewState}
            onRegenerate={onGenerate}
            defaultFilename={defaultFilename}
          />
        </div>
      </main>
    </div>
  );
}

function RecoveryNotice({
  message,
  detail,
  linkLabel,
}: {
  message: string;
  detail?: ReactNode;
  linkLabel: string;
}) {
  return (
    <div className="editor-theme flex flex-1 flex-col items-center justify-center gap-3 bg-ed-canvas px-8 py-20 text-center font-sans">
      <p className="text-[15px] font-medium text-ed-strong">{message}</p>
      {detail && <p className="max-w-sm text-[13px] text-ed-muted">{detail}</p>}
      <Link href="/" className="ed-btn ed-btn-primary mt-2">
        {linkLabel}
      </Link>
    </div>
  );
}
