"use client";

import { useCallback, useState } from "react";
import { BackendStatus } from "@/components/BackendStatus";
import { TrackSlot } from "@/components/TrackSlot";
import { TransitionAnchorSummary } from "@/components/TransitionAnchorSummary";
import { TransitionEditor, type SuggestionInfo } from "@/components/TransitionEditor";
import { TransitionOptionsPanel } from "@/components/TransitionOptionsPanel";
import { TransitionPreviewPanel } from "@/components/TransitionPreviewPanel";
import { useBeatAnchorControls } from "@/hooks/useBeatAnchorControls";
import { useTransitionPreview } from "@/hooks/useTransitionPreview";
import { useTransitionSuggestion } from "@/hooks/useTransitionSuggestion";
import { useVariantPreview } from "@/hooks/useVariantPreview";
import { EMPTY_BEATS } from "@/lib/beats";
import type { TrackAnalysis, TransitionSuggestion, TransitionVariant } from "@/lib/api";
import {
  DEFAULT_MIX_SETTINGS,
  DEFAULT_SONG_B_TEMPO_MULTIPLIER,
  clampBassSwapPosition,
  clampCrossfadeBias,
  clampGainDb,
  createInitialTransitionPlan,
  type BassSwapWidthBeats,
  type BeatAnchor,
  type TransitionBeats,
  type TransitionPlan,
  type TransitionStyle,
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

  const suggestion = useTransitionSuggestion();
  const variantPreview = useVariantPreview();

  // The suggestion whose variant was most recently adopted into the editor
  // — distinct from `suggestion.state`, which just tracks the latest
  // /transitions/suggest fetch (options can be fetched again without
  // disturbing whatever was already adopted into the editable plan).
  const [adoptedSuggestion, setAdoptedSuggestion] = useState<TransitionSuggestion | null>(
    null,
  );

  // The single centralized place a TransitionVariant's plan is copied into
  // the editable TransitionPlan — "Use in editor" is the only caller.
  const applyVariant = useCallback(
    (adopted: TransitionSuggestion, variant: TransitionVariant) => {
      applyPlanUpdate(() => ({
        songAAnchor: variant.plan.songAAnchor,
        songBAnchor: variant.plan.songBAnchor,
        transitionBeats: variant.plan.transitionBeats,
        songAGainDb: variant.plan.songAGainDb,
        songBGainDb: variant.plan.songBGainDb,
        crossfadeBias: variant.plan.crossfadeBias,
        songBTempoMultiplier: variant.plan.songBTempoMultiplier,
        transitionStyle: variant.plan.transitionStyle,
        bassSwapPosition: variant.plan.bassSwapPosition,
        bassSwapWidthBeats: variant.plan.bassSwapWidthBeats,
      }));
      setIsSuggestionEdited(false);
      setAdoptedSuggestion(adopted);
      // The editor's own preview system now owns this plan — clear the
      // option-preview player so it doesn't linger as if it still
      // represented a live, up-to-date view of the (now editable) plan.
      variantPreview.reset();
    },
    [applyPlanUpdate, variantPreview],
  );

  const handleUseInEditor = useCallback(
    (variant: TransitionVariant) => {
      if (suggestion.state.status !== "success") return;
      applyVariant(suggestion.state.suggestion, variant);
    },
    [suggestion.state, applyVariant],
  );

  const handlePreviewVariant = useCallback(
    (variant: TransitionVariant) => {
      if (!songAFile || !songAAnalysis || !songBFile || !songBAnalysis) return;
      variantPreview.previewVariant({
        variant,
        songAFile,
        songBFile,
        songAAnalysis,
        songBAnalysis,
      });
    },
    [songAFile, songAAnalysis, songBFile, songBAnalysis, variantPreview],
  );

  // Clears suggestion/adoption metadata (and the edited flag) together —
  // used whenever a track's file/analysis changes, since none of it still
  // describes the current inputs.
  const clearSuggestion = useCallback(() => {
    suggestion.clear();
    variantPreview.reset();
    setAdoptedSuggestion(null);
    setIsSuggestionEdited(false);
  }, [suggestion, variantPreview]);

  // A source track's FILE identity changing (replace or remove) means the
  // whole pair the current plan was built for is gone: every anchor, mix
  // setting, and tempo interpretation on the plan was chosen relative to
  // the OLD pairing (e.g. songBTempoMultiplier only means something
  // relative to both tracks' BPMs together), so the plan starts over
  // completely rather than partially — same fresh shape as first load.
  const resetPlanForNewTrackPair = useCallback(() => {
    setTransitionPlan(createInitialTransitionPlan());
    preview.reset();
    clearSuggestion();
  }, [preview, clearSuggestion]);

  const handleSongAFileChange = useCallback(
    (file: File | null) => {
      setSongAFile(file);
      resetPlanForNewTrackPair();
    },
    [resetPlanForNewTrackPair],
  );
  // Re-analyzing the SAME file is lighter-weight: it must invalidate the
  // preview and any suggestion/variant/adopted metadata (none of it still
  // describes the fresh analysis), but must NOT reset mix settings or the
  // other track's anchor — LoadedTrack already refreshes-or-clears this
  // track's own anchor beforehand (see its handleAnalysisSuccess) using
  // the updated beats array, which this deliberately leaves untouched.
  //
  // songBTempoMultiplier is the one plan field that's an exception:
  // it's derived from the BPM *relationship* between both analyses, not a
  // user-facing mix control, so it's reset to 1 here rather than preserved
  // — a stale multiplier could silently misdescribe the new BPM(s). "Find
  // transitions" can choose the correct multiplier again from there.
  const invalidateTempoMultiplier = useCallback(() => {
    setTransitionPlan((plan) => ({
      ...plan,
      songBTempoMultiplier: DEFAULT_SONG_B_TEMPO_MULTIPLIER,
    }));
  }, []);

  const handleSongAAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongAAnalysis(analysis);
      invalidateTempoMultiplier();
      preview.reset();
      clearSuggestion();
    },
    [invalidateTempoMultiplier, preview, clearSuggestion],
  );
  const handleSongBFileChange = useCallback(
    (file: File | null) => {
      setSongBFile(file);
      resetPlanForNewTrackPair();
    },
    [resetPlanForNewTrackPair],
  );
  const handleSongBAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongBAnalysis(analysis);
      invalidateTempoMultiplier();
      preview.reset();
      clearSuggestion();
    },
    [invalidateTempoMultiplier, preview, clearSuggestion],
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
      updatePlan((plan) => ({
        ...plan,
        transitionBeats: beats,
        // A shorter/longer transition changes what positions are valid
        // for the current bass-swap width — clamp so it never ends up
        // pointing outside the new transition's bounds.
        bassSwapPosition: clampBassSwapPosition(
          plan.bassSwapPosition,
          beats,
          plan.bassSwapWidthBeats,
        ),
      }));
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

  const handleTransitionStyleChange = useCallback(
    (style: TransitionStyle) => {
      updatePlan((plan) => ({ ...plan, transitionStyle: style }));
    },
    [updatePlan],
  );
  const handleBassSwapPositionChange = useCallback(
    (position: number) => {
      updatePlan((plan) => ({
        ...plan,
        bassSwapPosition: clampBassSwapPosition(
          position,
          plan.transitionBeats,
          plan.bassSwapWidthBeats,
        ),
      }));
    },
    [updatePlan],
  );
  const handleBassSwapWidthChange = useCallback(
    (width: BassSwapWidthBeats) => {
      updatePlan((plan) => ({
        ...plan,
        bassSwapWidthBeats: width,
        // Widening/narrowing the swap window can push the current
        // position out of range — clamp rather than leave a plan that
        // would begin with Song B's bass already partially active (or
        // end with Song A's still partially active).
        bassSwapPosition: clampBassSwapPosition(
          plan.bassSwapPosition,
          plan.transitionBeats,
          width,
        ),
      }));
    },
    [updatePlan],
  );

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

  // Deliberately excludes songBTempoMultiplier — it isn't a "mix setting"
  // Reset touches (see its doc comment in transitionPlan.ts), so it must
  // not affect whether the Reset button reads as already-at-defaults.
  const isMixAtDefaults =
    transitionPlan.transitionBeats === DEFAULT_MIX_SETTINGS.transitionBeats &&
    transitionPlan.songAGainDb === DEFAULT_MIX_SETTINGS.songAGainDb &&
    transitionPlan.songBGainDb === DEFAULT_MIX_SETTINGS.songBGainDb &&
    transitionPlan.crossfadeBias === DEFAULT_MIX_SETTINGS.crossfadeBias &&
    transitionPlan.transitionStyle === DEFAULT_MIX_SETTINGS.transitionStyle &&
    transitionPlan.bassSwapPosition === DEFAULT_MIX_SETTINGS.bassSwapPosition &&
    transitionPlan.bassSwapWidthBeats === DEFAULT_MIX_SETTINGS.bassSwapWidthBeats;

  const handleFindTransitions = () => {
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
      transitionStyle: transitionPlan.transitionStyle,
      bassSwapPosition: transitionPlan.bassSwapPosition,
      bassSwapWidthBeats: transitionPlan.bassSwapWidthBeats,
    });
  };

  // Reflects whichever suggestion the CURRENT editable plan was actually
  // adopted from — not necessarily the latest /transitions/suggest fetch,
  // since options can be re-fetched without disturbing an already-adopted
  // plan (see applyVariant/adoptedSuggestion above).
  const suggestionInfo: SuggestionInfo | null =
    adoptedSuggestion && songBAnalysis
      ? {
          tempoCompatibility: adoptedSuggestion.tempoCompatibility,
          usedTempoNormalization: adoptedSuggestion.usedTempoNormalization,
          songBRawBpm: songBAnalysis.tempoBpm,
          effectiveSongBBpm: adoptedSuggestion.effectiveSongBBpm,
          isEdited: isSuggestionEdited,
          harmonicCompatibility: adoptedSuggestion.harmonicCompatibility,
          songALocalKey: adoptedSuggestion.songALocalKey,
          songALocalMode: adoptedSuggestion.songALocalMode,
          songBLocalKey: adoptedSuggestion.songBLocalKey,
          songBLocalMode: adoptedSuggestion.songBLocalMode,
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
          <TransitionOptionsPanel
            suggestionState={suggestion.state}
            onFindTransitions={handleFindTransitions}
            variantPreviewState={variantPreview.state}
            onPreviewVariant={handlePreviewVariant}
            onUseInEditor={handleUseInEditor}
          />
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
            onTransitionStyleChange={handleTransitionStyleChange}
            onBassSwapPositionChange={handleBassSwapPositionChange}
            onBassSwapWidthChange={handleBassSwapWidthChange}
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
