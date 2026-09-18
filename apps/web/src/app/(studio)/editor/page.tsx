"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Deck } from "@/components/Deck";
import { TransitionAnchorSummary } from "@/components/TransitionAnchorSummary";
import { TransitionCurveVisualization } from "@/components/TransitionCurveVisualization";
import { TransitionMixer } from "@/components/TransitionMixer";
import { TransitionPreviewPanel } from "@/components/TransitionPreviewPanel";
import { useStudio } from "@/context/StudioContext";

/**
 * The DJ-style transition workstation: Deck A / Mixer / Deck B, then the
 * enlarged transition visualization, then preview/export. Everything
 * here reads from and writes to the same StudioContext the setup page
 * uses — nothing is re-implemented, only laid out differently.
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
    <div className="flex flex-1 flex-col bg-white dark:bg-black">
      <header className="flex items-center justify-between gap-4 px-8 py-6 sm:px-12">
        <Link
          href="/"
          className="text-sm text-zinc-500 underline-offset-4 hover:underline dark:text-zinc-400"
        >
          ← Back to tracks
        </Link>
      </header>

      <main className="flex flex-1 flex-col gap-8 px-4 pb-20 sm:px-8">
        {/* DOM order is Deck A, Deck B, Mixer so mobile (single column,
            no order overrides apply) stacks exactly as specified: Deck A,
            Deck B, Mixer. At lg+, Deck B is pushed after the Mixer via
            `lg:order-3` (Deck A and the Mixer, both left at the default
            order, keep their DOM order — Deck A before Mixer — giving
            the desired Deck A | Mixer | Deck B composition). The Mixer's
            column is intentionally a touch narrower than the decks at
            desktop width (a real workstation's center strip usually is)
            via the lg-only column-width override on the grid itself. */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-[1fr_0.85fr_1fr]">
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
          <div className="lg:order-3">
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
          <div className="md:col-span-2 lg:col-span-1">
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
              isGenerating={previewState.status === "generating"}
              isMixAtDefaults={isMixAtDefaults}
            />
          </div>
        </div>

        <TransitionAnchorSummary plan={transitionPlan} />

        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-200 bg-zinc-50/60 p-6 dark:border-zinc-800 dark:bg-zinc-950/40">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-400 dark:text-zinc-500">
            Transition visualization
          </h2>
          <div className="mx-auto w-full max-w-3xl">
            <TransitionCurveVisualization plan={transitionPlan} />
          </div>
        </section>

        <TransitionPreviewPanel
          state={previewState}
          onRegenerate={onGenerate}
          defaultFilename={defaultFilename}
        />
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
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 py-20 text-center">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{message}</p>
      {detail && <p className="max-w-sm text-xs text-zinc-500 dark:text-zinc-500">{detail}</p>}
      <Link
        href="/"
        className="mt-1 rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
      >
        {linkLabel}
      </Link>
    </div>
  );
}
