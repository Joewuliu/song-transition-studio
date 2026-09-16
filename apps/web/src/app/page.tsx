"use client";

import { useCallback, useState } from "react";
import { BackendStatus } from "@/components/BackendStatus";
import { TrackSlot } from "@/components/TrackSlot";
import { TransitionAnchorSummary } from "@/components/TransitionAnchorSummary";
import { TransitionEditor, type SuggestionInfo } from "@/components/TransitionEditor";
import { TransitionPreviewPanel } from "@/components/TransitionPreviewPanel";
import { useBeatAnchorControls } from "@/hooks/useBeatAnchorControls";
import { useTransitionPreview } from "@/hooks/useTransitionPreview";
import { useTransitionSuggestion } from "@/hooks/useTransitionSuggestion";
import { EMPTY_BEATS } from "@/lib/beats";
import type { TrackAnalysis, TransitionSuggestion } from "@/lib/api";
import {
  DEFAULT_MIX_SETTINGS,
  clampCrossfadeBias,
  clampGainDb,
  createInitialTransitionPlan,
  type BeatAnchor,
  type TransitionBeats,
  type TransitionPlan,
} from "@/lib/transitionPlan";

export default function Home() {
  const [songAFile, setSongAFile] = useState<File | null>(null);
  const [songAAnalysis, setSongAAnalysis] = useState<TrackAnalysis | null>(null);

  const [songBFile, setSongBFile] = useState<File | null>(null);
  const [songBAnalysis, setSongBAnalysis] = useState<TrackAnalysis | null>(null);

  // The authoritative editor state: anchors plus every mix parameter the
  // editor (or a suggestion) controls. Always updated immutably (spread
  // into a new object), via the narrow helpers below.
  const [transitionPlan, setTransitionPlan] = useState<TransitionPlan>(
    createInitialTransitionPlan(),
  );

  const preview = useTransitionPreview();

  // Tracks whether the plan has been manually changed since the most
  // recent suggestion was applied — purely a label concern (see
  // suggestionInfo below); it never affects preview staleness, source
  // track state, or rendering.
  const [isSuggestionEdited, setIsSuggestionEdited] = useState(false);

  // Low-level: mutate the plan and mark the preview stale, without
  // touching suggestion-edited tracking. Used both by applySuggestion
  // (which explicitly resets that flag itself) and by updatePlan below.
  const applyPlanUpdate = useCallback(
    (updater: (plan: TransitionPlan) => TransitionPlan) => {
      setTransitionPlan(updater);
      preview.markStale();
    },
    [preview],
  );

  // Every user-facing edit (anchor, length, gain, bias) goes through this:
  // it marks a successful preview stale rather than destroying it, so the
  // user can keep comparing it while they tune parameters, and it marks
  // any current suggestion as edited (a label change only).
  const updatePlan = useCallback(
    (updater: (plan: TransitionPlan) => TransitionPlan) => {
      applyPlanUpdate(updater);
      setIsSuggestionEdited(true);
    },
    [applyPlanUpdate],
  );

  const applySuggestion = useCallback(
    (suggestion: TransitionSuggestion) => {
      applyPlanUpdate(() => ({
        songAAnchor: suggestion.plan.songAAnchor,
        songBAnchor: suggestion.plan.songBAnchor,
        transitionBeats: suggestion.plan.transitionBeats,
        songAGainDb: suggestion.plan.songAGainDb,
        songBGainDb: suggestion.plan.songBGainDb,
        crossfadeBias: suggestion.plan.crossfadeBias,
        songBTempoMultiplier: suggestion.plan.songBTempoMultiplier,
      }));
      setIsSuggestionEdited(false);
    },
    [applyPlanUpdate],
  );

  const suggestion = useTransitionSuggestion({ onSuggested: applySuggestion });

  // Clears suggestion metadata (and its edited flag) together — used
  // whenever a track's file/analysis changes, since the suggestion no
  // longer describes the current inputs.
  const clearSuggestion = useCallback(() => {
    suggestion.clear();
    setIsSuggestionEdited(false);
  }, [suggestion]);

  // A source track's file/analysis changing invalidates the preview
  // entirely (rendered from audio that may no longer be loaded) and clears
  // any suggestion metadata (it no longer describes the current inputs).
  const handleSongAFileChange = useCallback(
    (file: File | null) => {
      setSongAFile(file);
      preview.reset();
      clearSuggestion();
    },
    [preview, clearSuggestion],
  );
  const handleSongAAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongAAnalysis(analysis);
      preview.reset();
      clearSuggestion();
    },
    [preview, clearSuggestion],
  );
  const handleSongBFileChange = useCallback(
    (file: File | null) => {
      setSongBFile(file);
      preview.reset();
      clearSuggestion();
    },
    [preview, clearSuggestion],
  );
  const handleSongBAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongBAnalysis(analysis);
      preview.reset();
      clearSuggestion();
    },
    [preview, clearSuggestion],
  );

  // An anchor becoming null only happens when its track is replaced or
  // removed (TrackSlot's own doing) — that's a full invalidation, not an
  // edit. An anchor becoming a real value is a genuine, stale-marking edit.
  const handleSongAAnchorChange = useCallback(
    (anchor: BeatAnchor | null) => {
      if (anchor === null) {
        setTransitionPlan((plan) => ({ ...plan, songAAnchor: null }));
        preview.reset();
      } else {
        updatePlan((plan) => ({ ...plan, songAAnchor: anchor }));
      }
    },
    [preview, updatePlan],
  );
  const handleSongBAnchorChange = useCallback(
    (anchor: BeatAnchor | null) => {
      if (anchor === null) {
        setTransitionPlan((plan) => ({ ...plan, songBAnchor: null }));
        preview.reset();
      } else {
        updatePlan((plan) => ({ ...plan, songBAnchor: anchor }));
      }
    },
    [preview, updatePlan],
  );

  const handleTransitionBeatsChange = useCallback(
    (beats: TransitionBeats) => {
      updatePlan((plan) => ({ ...plan, transitionBeats: beats }));
    },
    [updatePlan],
  );
  const handleSongAGainChange = useCallback(
    (db: number) => {
      updatePlan((plan) => ({ ...plan, songAGainDb: clampGainDb(db) }));
    },
    [updatePlan],
  );
  const handleSongBGainChange = useCallback(
    (db: number) => {
      updatePlan((plan) => ({ ...plan, songBGainDb: clampGainDb(db) }));
    },
    [updatePlan],
  );
  const handleCrossfadeBiasChange = useCallback(
    (bias: number) => {
      updatePlan((plan) => ({ ...plan, crossfadeBias: clampCrossfadeBias(bias) }));
    },
    [updatePlan],
  );
  const handleResetMixSettings = useCallback(() => {
    updatePlan((plan) => ({ ...plan, ...DEFAULT_MIX_SETTINGS }));
  }, [updatePlan]);

  const songABeats = songAAnalysis?.beats ?? EMPTY_BEATS;
  const songBBeats = songBAnalysis?.beats ?? EMPTY_BEATS;

  // Same underlying anchor value as the waveform's click-to-seek — this
  // just gives the editor its own previous/next controls over it.
  const songAAnchorControls = useBeatAnchorControls({
    beats: songABeats,
    anchor: transitionPlan.songAAnchor,
    onAnchorChange: handleSongAAnchorChange,
  });
  const songBAnchorControls = useBeatAnchorControls({
    beats: songBBeats,
    anchor: transitionPlan.songBAnchor,
    onAnchorChange: handleSongBAnchorChange,
  });

  const canSuggest = songAAnalysis !== null && songBAnalysis !== null;

  const canGenerate =
    songAFile !== null &&
    songAAnalysis !== null &&
    transitionPlan.songAAnchor !== null &&
    songBFile !== null &&
    songBAnalysis !== null &&
    transitionPlan.songBAnchor !== null;

  const isMixAtDefaults =
    transitionPlan.transitionBeats === DEFAULT_MIX_SETTINGS.transitionBeats &&
    transitionPlan.songAGainDb === DEFAULT_MIX_SETTINGS.songAGainDb &&
    transitionPlan.songBGainDb === DEFAULT_MIX_SETTINGS.songBGainDb &&
    transitionPlan.crossfadeBias === DEFAULT_MIX_SETTINGS.crossfadeBias &&
    transitionPlan.songBTempoMultiplier === DEFAULT_MIX_SETTINGS.songBTempoMultiplier;

  const handleSuggest = () => {
    if (!canSuggest || suggestion.state.status === "suggesting") return;
    if (!songAAnalysis || !songBAnalysis) return;
    suggestion.suggest(songAAnalysis, songBAnalysis);
  };

  const handleGenerate = () => {
    if (
      !canGenerate ||
      preview.state.status === "generating" ||
      !songAFile ||
      !songAAnalysis ||
      !transitionPlan.songAAnchor ||
      !songBFile ||
      !songBAnalysis ||
      !transitionPlan.songBAnchor
    ) {
      return;
    }

    preview.generate({
      songAFile,
      songBFile,
      songAAnalysis,
      songBAnalysis,
      songAAnchor: transitionPlan.songAAnchor,
      songBAnchor: transitionPlan.songBAnchor,
      transitionBeats: transitionPlan.transitionBeats,
      songAGainDb: transitionPlan.songAGainDb,
      songBGainDb: transitionPlan.songBGainDb,
      crossfadeBias: transitionPlan.crossfadeBias,
      songBTempoMultiplier: transitionPlan.songBTempoMultiplier,
    });
  };

  const suggestionInfo: SuggestionInfo | null =
    suggestion.state.status === "success" && songBAnalysis
      ? {
          tempoCompatibility: suggestion.state.suggestion.tempoCompatibility,
          usedTempoNormalization: suggestion.state.suggestion.usedTempoNormalization,
          songBRawBpm: songBAnalysis.tempoBpm,
          effectiveSongBBpm: suggestion.state.suggestion.effectiveSongBBpm,
          isEdited: isSuggestionEdited,
        }
      : null;

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
          anchor={transitionPlan.songAAnchor}
          onAnchorChange={handleSongAAnchorChange}
        />
        <TrackSlot
          label="Song B"
          accent="teal"
          file={songBFile}
          onFileChange={handleSongBFileChange}
          onAnalysisChange={handleSongBAnalysisChange}
          anchor={transitionPlan.songBAnchor}
          onAnchorChange={handleSongBAnchorChange}
        />

        {canSuggest && (
          <section className="flex flex-col gap-3 border-t border-zinc-200 pt-6 dark:border-zinc-800">
            <button
              type="button"
              onClick={handleSuggest}
              disabled={suggestion.state.status === "suggesting"}
              className="self-start rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-zinc-400 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-200"
            >
              {suggestion.state.status === "suggesting"
                ? "Suggesting…"
                : suggestion.state.status === "success"
                  ? "Suggest again"
                  : "Suggest transition"}
            </button>
            {suggestion.state.status === "error" && (
              <p className="text-xs text-red-500">{suggestion.state.message}</p>
            )}
          </section>
        )}

        <TransitionAnchorSummary plan={transitionPlan} />

        {canGenerate && (
          <TransitionEditor
            plan={transitionPlan}
            suggestionInfo={suggestionInfo}
            songAAnchorControls={songAAnchorControls}
            songBAnchorControls={songBAnchorControls}
            onTransitionBeatsChange={handleTransitionBeatsChange}
            onSongAGainChange={handleSongAGainChange}
            onSongBGainChange={handleSongBGainChange}
            onCrossfadeBiasChange={handleCrossfadeBiasChange}
            onResetMixSettings={handleResetMixSettings}
            onGenerate={handleGenerate}
            isGenerating={preview.state.status === "generating"}
            isMixAtDefaults={isMixAtDefaults}
          />
        )}

        <TransitionPreviewPanel state={preview.state} onRegenerate={handleGenerate} />
      </main>
    </div>
  );
}
