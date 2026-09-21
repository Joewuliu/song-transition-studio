"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useTransitionPreview, type TransitionPreviewState } from "@/hooks/useTransitionPreview";
import {
  useTransitionSuggestion,
  type TransitionSuggestionState,
} from "@/hooks/useTransitionSuggestion";
import { useVariantPreview, type VariantPreviewState } from "@/hooks/useVariantPreview";
import { defaultExportFilename } from "@/lib/export";
import type {
  MusicalMode,
  PitchClass,
  TempoCompatibility,
  TrackAnalysis,
  TransitionChoice,
  TransitionSuggestion,
} from "@/lib/api";
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

/** Everything the editor's suggestion banner needs, resolved from
 * whichever suggestion the CURRENT plan was actually adopted from — see
 * `adoptedSuggestion` below. Kept separate from the raw API shape so the
 * mixer never needs to know about internal field names like
 * `crossfadeBias`/`songBTempoMultiplier`. */
export interface SuggestionInfo {
  tempoCompatibility: TempoCompatibility;
  usedTempoNormalization: boolean;
  songBRawBpm: number;
  effectiveSongBBpm: number;
  isEdited: boolean;
  harmonicCompatibility: number;
  songALocalKey: PitchClass | null;
  songALocalMode: MusicalMode | null;
  songBLocalKey: PitchClass | null;
  songBLocalMode: MusicalMode | null;
}

interface StudioContextValue {
  songAFile: File | null;
  songBFile: File | null;
  songAAnalysis: TrackAnalysis | null;
  songBAnalysis: TrackAnalysis | null;
  onSongAFileChange: (file: File | null) => void;
  onSongAAnalysisChange: (analysis: TrackAnalysis | null) => void;
  onSongBFileChange: (file: File | null) => void;
  onSongBAnalysisChange: (analysis: TrackAnalysis | null) => void;

  transitionPlan: TransitionPlan;
  onSongAAnchorChange: (anchor: BeatAnchor | null) => void;
  onSongBAnchorChange: (anchor: BeatAnchor | null) => void;
  onTransitionBeatsChange: (beats: TransitionBeats) => void;
  onSongAGainChange: (db: number) => void;
  onSongBGainChange: (db: number) => void;
  onCrossfadeBiasChange: (bias: number) => void;
  onResetMixSettings: () => void;
  onTransitionStyleChange: (style: TransitionStyle) => void;
  onBassSwapPositionChange: (position: number) => void;
  onBassSwapWidthChange: (width: BassSwapWidthBeats) => void;
  isMixAtDefaults: boolean;

  canSuggest: boolean;
  suggestionState: TransitionSuggestionState;
  onFindTransitions: () => void;
  variantPreviewState: VariantPreviewState;
  onPreviewVariant: (variant: TransitionChoice) => void;
  /** Adopts the choice into the editable plan AND navigates to /editor —
   * "Use in editor" is the only caller. */
  onUseInEditor: (variant: TransitionChoice) => void;
  suggestionInfo: SuggestionInfo | null;

  canGenerate: boolean;
  previewState: TransitionPreviewState;
  isPreviewFreshAndExportable: boolean;
  onGenerate: () => void;
  defaultFilename: string;
}

const StudioContext = createContext<StudioContextValue | null>(null);

/**
 * Owns every piece of workspace state that both / (setup) and /editor
 * (workstation) need — source files, their analyses, the editable
 * TransitionPlan, suggestion/variant state, and preview/export state.
 * Mounted once in the (studio) route group's layout, so this instance
 * (and everything in it) survives client-side navigation between the two
 * pages: nothing here is duplicated per-page, and nothing is persisted
 * beyond memory (no URL params, no localStorage) — a full reload always
 * starts fresh, by design (see the /editor recovery state).
 */
export function StudioProvider({ children }: { children: ReactNode }) {
  const router = useRouter();

  const [songAFile, setSongAFile] = useState<File | null>(null);
  const [songAAnalysis, setSongAAnalysis] = useState<TrackAnalysis | null>(null);
  const [songBFile, setSongBFile] = useState<File | null>(null);
  const [songBAnalysis, setSongBAnalysis] = useState<TrackAnalysis | null>(null);

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
  // touching suggestion-edited tracking.
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

  // The suggestion + specific choice most recently adopted into the
  // editor — distinct from `suggestion.state`, which just tracks the
  // latest /transitions/suggest fetch (options can be fetched again
  // without disturbing whatever was already adopted into the plan). The
  // outer suggestion carries tempo interpretation (shared by every
  // choice); the choice itself carries the harmonic context specific to
  // the anchors that were actually adopted.
  const [adopted, setAdopted] = useState<{
    suggestion: TransitionSuggestion;
    choice: TransitionChoice;
  } | null>(null);

  // The single centralized place a TransitionChoice's plan is copied into
  // the editable TransitionPlan.
  const applyVariant = useCallback(
    (suggestion: TransitionSuggestion, variant: TransitionChoice) => {
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
      setAdopted({ suggestion, choice: variant });
      // The editor's own preview system now owns this plan — clear the
      // option-preview player so it doesn't linger as if it still
      // represented a live, up-to-date view of the (now editable) plan.
      variantPreview.reset();
    },
    [applyPlanUpdate, variantPreview],
  );

  const onUseInEditor = useCallback(
    (variant: TransitionChoice) => {
      if (suggestion.state.status !== "success") return;
      applyVariant(suggestion.state.suggestion, variant);
      router.push("/editor");
    },
    [suggestion.state, applyVariant, router],
  );

  const onPreviewVariant = useCallback(
    (variant: TransitionChoice) => {
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
  // used whenever a track's file/analysis changes, since none of it
  // still describes the current inputs.
  const clearSuggestion = useCallback(() => {
    suggestion.clear();
    variantPreview.reset();
    setAdopted(null);
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

  const onSongAFileChange = useCallback(
    (file: File | null) => {
      setSongAFile(file);
      resetPlanForNewTrackPair();
    },
    [resetPlanForNewTrackPair],
  );
  const onSongBFileChange = useCallback(
    (file: File | null) => {
      setSongBFile(file);
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
  // songBTempoMultiplier is the one plan field that's an exception: it's
  // derived from the BPM *relationship* between both analyses, not a
  // user-facing mix control, so it's reset to 1 here rather than
  // preserved — a stale multiplier could silently misdescribe the new
  // BPM(s). "Find transitions" can choose the correct multiplier again.
  const invalidateTempoMultiplier = useCallback(() => {
    setTransitionPlan((plan) => ({
      ...plan,
      songBTempoMultiplier: DEFAULT_SONG_B_TEMPO_MULTIPLIER,
    }));
  }, []);

  const onSongAAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongAAnalysis(analysis);
      invalidateTempoMultiplier();
      preview.reset();
      clearSuggestion();
    },
    [invalidateTempoMultiplier, preview, clearSuggestion],
  );
  const onSongBAnalysisChange = useCallback(
    (analysis: TrackAnalysis | null) => {
      setSongBAnalysis(analysis);
      invalidateTempoMultiplier();
      preview.reset();
      clearSuggestion();
    },
    [invalidateTempoMultiplier, preview, clearSuggestion],
  );

  // An anchor becoming null only happens when its track is replaced or
  // removed — that's a full invalidation, not an edit. An anchor
  // becoming a real value is a genuine, stale-marking edit.
  const onSongAAnchorChange = useCallback(
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
  const onSongBAnchorChange = useCallback(
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

  const onTransitionBeatsChange = useCallback(
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
  const onSongAGainChange = useCallback(
    (db: number) => {
      updatePlan((plan) => ({ ...plan, songAGainDb: clampGainDb(db) }));
    },
    [updatePlan],
  );
  const onSongBGainChange = useCallback(
    (db: number) => {
      updatePlan((plan) => ({ ...plan, songBGainDb: clampGainDb(db) }));
    },
    [updatePlan],
  );
  const onCrossfadeBiasChange = useCallback(
    (bias: number) => {
      updatePlan((plan) => ({ ...plan, crossfadeBias: clampCrossfadeBias(bias) }));
    },
    [updatePlan],
  );
  const onResetMixSettings = useCallback(() => {
    updatePlan((plan) => ({ ...plan, ...DEFAULT_MIX_SETTINGS }));
  }, [updatePlan]);

  const onTransitionStyleChange = useCallback(
    (style: TransitionStyle) => {
      updatePlan((plan) => ({ ...plan, transitionStyle: style }));
    },
    [updatePlan],
  );
  const onBassSwapPositionChange = useCallback(
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
  const onBassSwapWidthChange = useCallback(
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

  const canSuggest = songAAnalysis !== null && songBAnalysis !== null;

  const canGenerate =
    songAFile !== null &&
    songAAnalysis !== null &&
    transitionPlan.songAAnchor !== null &&
    songBFile !== null &&
    songBAnalysis !== null &&
    transitionPlan.songBAnchor !== null;

  // Export eligibility derives from the SAME preview state the player
  // itself renders from — never a separate boolean that could drift out
  // of sync with what's actually currently playable.
  const isPreviewFreshAndExportable =
    preview.state.status === "success" && !preview.state.isStale;

  // Deliberately excludes songBTempoMultiplier — it isn't a "mix
  // setting" Reset touches, so it must not affect whether the Reset
  // button reads as already-at-defaults.
  const isMixAtDefaults =
    transitionPlan.transitionBeats === DEFAULT_MIX_SETTINGS.transitionBeats &&
    transitionPlan.songAGainDb === DEFAULT_MIX_SETTINGS.songAGainDb &&
    transitionPlan.songBGainDb === DEFAULT_MIX_SETTINGS.songBGainDb &&
    transitionPlan.crossfadeBias === DEFAULT_MIX_SETTINGS.crossfadeBias &&
    transitionPlan.transitionStyle === DEFAULT_MIX_SETTINGS.transitionStyle &&
    transitionPlan.bassSwapPosition === DEFAULT_MIX_SETTINGS.bassSwapPosition &&
    transitionPlan.bassSwapWidthBeats === DEFAULT_MIX_SETTINGS.bassSwapWidthBeats;

  const onFindTransitions = useCallback(() => {
    if (!canSuggest || suggestion.state.status === "suggesting") return;
    if (!songAAnalysis || !songBAnalysis) return;
    suggestion.suggest(songAAnalysis, songBAnalysis);
  }, [canSuggest, suggestion, songAAnalysis, songBAnalysis]);

  const onGenerate = useCallback(() => {
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
  }, [canGenerate, preview, songAFile, songAAnalysis, songBFile, songBAnalysis, transitionPlan]);

  // Reflects whichever suggestion/choice the CURRENT editable plan was
  // actually adopted from — not necessarily the latest /transitions/
  // suggest fetch, since options can be re-fetched without disturbing an
  // already-adopted plan (see applyVariant/adopted above). Tempo
  // interpretation comes from the outer suggestion (shared by every
  // choice); harmonic context comes from the specific choice adopted.
  const suggestionInfo: SuggestionInfo | null =
    adopted && songBAnalysis
      ? {
          tempoCompatibility: adopted.suggestion.tempoCompatibility,
          usedTempoNormalization: adopted.suggestion.usedTempoNormalization,
          songBRawBpm: songBAnalysis.tempoBpm,
          effectiveSongBBpm: adopted.suggestion.effectiveSongBBpm,
          isEdited: isSuggestionEdited,
          harmonicCompatibility: adopted.choice.harmonicCompatibility,
          songALocalKey: adopted.choice.songALocalKey,
          songALocalMode: adopted.choice.songALocalMode,
          songBLocalKey: adopted.choice.songBLocalKey,
          songBLocalMode: adopted.choice.songBLocalMode,
        }
      : null;

  const defaultFilename = defaultExportFilename(
    songAFile?.name ?? "song-a",
    songBFile?.name ?? "song-b",
  );

  const value: StudioContextValue = {
    songAFile,
    songBFile,
    songAAnalysis,
    songBAnalysis,
    onSongAFileChange,
    onSongAAnalysisChange,
    onSongBFileChange,
    onSongBAnalysisChange,

    transitionPlan,
    onSongAAnchorChange,
    onSongBAnchorChange,
    onTransitionBeatsChange,
    onSongAGainChange,
    onSongBGainChange,
    onCrossfadeBiasChange,
    onResetMixSettings,
    onTransitionStyleChange,
    onBassSwapPositionChange,
    onBassSwapWidthChange,
    isMixAtDefaults,

    canSuggest,
    suggestionState: suggestion.state,
    onFindTransitions,
    variantPreviewState: variantPreview.state,
    onPreviewVariant,
    onUseInEditor,
    suggestionInfo,

    canGenerate,
    previewState: preview.state,
    isPreviewFreshAndExportable,
    onGenerate,
    defaultFilename,
  };

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

export function useStudio(): StudioContextValue {
  const context = useContext(StudioContext);
  if (context === null) {
    throw new Error("useStudio must be used within a StudioProvider");
  }
  return context;
}
