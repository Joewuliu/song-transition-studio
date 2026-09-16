import type {
  BeatAnchor,
  SongBTempoMultiplier,
  TransitionBeats,
} from "@/lib/transitionPlan";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
    if (!response.ok) return false;

    const data: unknown = await response.json();
    return (
      typeof data === "object" &&
      data !== null &&
      "status" in data &&
      data.status === "ok"
    );
  } catch {
    return false;
  }
}

/**
 * A beat that scored well as a potential transition entry/exit point —
 * not a downbeat, bar, or phrase boundary, just a beat near a locally
 * meaningful energy/onset change. The frontend doesn't currently render
 * these directly; they're carried on TrackAnalysis so /transitions/suggest
 * can use them without re-uploading audio.
 */
export interface TransitionCandidate {
  beatIndex: number;
  timeSeconds: number;
  score: number;
  boundaryStrength: number;
  energyBefore: number;
  energyAfter: number;
}

export interface TrackAnalysis {
  durationSeconds: number;
  tempoBpm: number;
  beatCount: number;
  beats: number[];
  entryCandidates: TransitionCandidate[];
  exitCandidates: TransitionCandidate[];
}

interface TransitionCandidateResponse {
  beat_index: number;
  time_seconds: number;
  score: number;
  boundary_strength: number;
  energy_before: number;
  energy_after: number;
}

interface TrackAnalysisResponse {
  duration_seconds: number;
  tempo_bpm: number;
  beat_count: number;
  beats: number[];
  entry_candidates: TransitionCandidateResponse[];
  exit_candidates: TransitionCandidateResponse[];
}

export class AnalyzeTrackError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "AnalyzeTrackError";
    this.status = status;
  }
}

export async function analyzeTrack(file: File): Promise<TrackAnalysis> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/tracks/analyze`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new AnalyzeTrackError(
      "Couldn't reach the analysis server. Is the backend running?",
    );
  }

  if (!response.ok) {
    throw new AnalyzeTrackError(await extractErrorDetail(response), response.status);
  }

  const data = (await response.json()) as TrackAnalysisResponse;

  return {
    durationSeconds: data.duration_seconds,
    tempoBpm: data.tempo_bpm,
    beatCount: data.beat_count,
    beats: data.beats,
    entryCandidates: data.entry_candidates.map(candidateFromResponse),
    exitCandidates: data.exit_candidates.map(candidateFromResponse),
  };
}

function candidateFromResponse(
  candidate: TransitionCandidateResponse,
): TransitionCandidate {
  return {
    beatIndex: candidate.beat_index,
    timeSeconds: candidate.time_seconds,
    score: candidate.score,
    boundaryStrength: candidate.boundary_strength,
    energyBefore: candidate.energy_before,
    energyAfter: candidate.energy_after,
  };
}

function candidateToRequestBody(
  candidate: TransitionCandidate,
): TransitionCandidateResponse {
  return {
    beat_index: candidate.beatIndex,
    time_seconds: candidate.timeSeconds,
    score: candidate.score,
    boundary_strength: candidate.boundaryStrength,
    energy_before: candidate.energyBefore,
    energy_after: candidate.energyAfter,
  };
}

function analysisToRequestBody(analysis: TrackAnalysis): TrackAnalysisResponse {
  return {
    duration_seconds: analysis.durationSeconds,
    tempo_bpm: analysis.tempoBpm,
    beat_count: analysis.beatCount,
    beats: analysis.beats,
    entry_candidates: analysis.entryCandidates.map(candidateToRequestBody),
    exit_candidates: analysis.exitCandidates.map(candidateToRequestBody),
  };
}

export interface RenderTransitionParams {
  songAFile: File;
  songBFile: File;
  songAAnchor: BeatAnchor;
  songBAnchor: BeatAnchor;
  songABpm: number;
  songBBpm: number;
  transitionBeats: TransitionBeats;
  songAGainDb: number;
  songBGainDb: number;
  crossfadeBias: number;
  songBTempoMultiplier: SongBTempoMultiplier;
}

export interface RenderedTransitionResult {
  wavBlob: Blob;
  targetBpm: number | null;
  durationSeconds: number | null;
}

export class RenderTransitionError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RenderTransitionError";
    this.status = status;
  }
}

export async function renderTransition(
  params: RenderTransitionParams,
): Promise<RenderedTransitionResult> {
  const formData = new FormData();
  formData.append("song_a", params.songAFile);
  formData.append("song_b", params.songBFile);
  formData.append(
    "plan",
    JSON.stringify({
      song_a_anchor: {
        beat_index: params.songAAnchor.beatIndex,
        time_seconds: params.songAAnchor.timeSeconds,
      },
      song_b_anchor: {
        beat_index: params.songBAnchor.beatIndex,
        time_seconds: params.songBAnchor.timeSeconds,
      },
      song_a_bpm: params.songABpm,
      song_b_bpm: params.songBBpm,
      transition_beats: params.transitionBeats,
      song_a_gain_db: params.songAGainDb,
      song_b_gain_db: params.songBGainDb,
      crossfade_bias: params.crossfadeBias,
      song_b_tempo_multiplier: params.songBTempoMultiplier,
    }),
  );

  let response: Response;
  try {
    response = await fetch(`${API_URL}/transitions/render`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new RenderTransitionError(
      "Couldn't reach the transition server. Is the backend running?",
    );
  }

  if (!response.ok) {
    throw new RenderTransitionError(
      await extractErrorDetail(response),
      response.status,
    );
  }

  const wavBlob = await response.blob();

  return {
    wavBlob,
    targetBpm: parseFiniteFloatHeader(response.headers.get("X-Target-Bpm")),
    durationSeconds: parseFiniteFloatHeader(
      response.headers.get("X-Preview-Duration-Seconds"),
    ),
  };
}

function parseFiniteFloatHeader(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export type TempoCompatibility =
  | "compatible"
  | "moderate"
  | "significant"
  | "extreme";
export type AnchorSource = "candidate" | "fallback";

export interface SuggestedTransitionPlan {
  songAAnchor: BeatAnchor;
  songBAnchor: BeatAnchor;
  transitionBeats: TransitionBeats;
  songAGainDb: number;
  songBGainDb: number;
  crossfadeBias: number;
  songBTempoMultiplier: SongBTempoMultiplier;
}

export interface TransitionSuggestion {
  plan: SuggestedTransitionPlan;
  effectiveSongBBpm: number;
  tempoCompatibility: TempoCompatibility;
  usedTempoNormalization: boolean;
  songAAnchorSource: AnchorSource;
  songBAnchorSource: AnchorSource;
}

interface TransitionSuggestResponseBody {
  plan: {
    song_a_anchor: { beat_index: number; time_seconds: number };
    song_b_anchor: { beat_index: number; time_seconds: number };
    transition_beats: TransitionBeats;
    song_a_gain_db: number;
    song_b_gain_db: number;
    crossfade_bias: number;
    song_b_tempo_multiplier: SongBTempoMultiplier;
  };
  effective_song_b_bpm: number;
  tempo_compatibility: TempoCompatibility;
  used_tempo_normalization: boolean;
  song_a_anchor_source: AnchorSource;
  song_b_anchor_source: AnchorSource;
}

export class SuggestTransitionError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "SuggestTransitionError";
    this.status = status;
  }
}

/**
 * Suggests a starting TransitionPlan from two already-computed analyses.
 * Deliberately upload-free: candidate/beat data already returned by
 * analyzeTrack is everything the planner needs.
 */
export async function suggestTransition(
  songAAnalysis: TrackAnalysis,
  songBAnalysis: TrackAnalysis,
): Promise<TransitionSuggestion> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/transitions/suggest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        song_a_analysis: analysisToRequestBody(songAAnalysis),
        song_b_analysis: analysisToRequestBody(songBAnalysis),
      }),
    });
  } catch {
    throw new SuggestTransitionError(
      "Couldn't reach the suggestion server. Is the backend running?",
    );
  }

  if (!response.ok) {
    throw new SuggestTransitionError(
      await extractErrorDetail(response),
      response.status,
    );
  }

  const data = (await response.json()) as TransitionSuggestResponseBody;

  return {
    plan: {
      songAAnchor: {
        beatIndex: data.plan.song_a_anchor.beat_index,
        timeSeconds: data.plan.song_a_anchor.time_seconds,
      },
      songBAnchor: {
        beatIndex: data.plan.song_b_anchor.beat_index,
        timeSeconds: data.plan.song_b_anchor.time_seconds,
      },
      transitionBeats: data.plan.transition_beats,
      songAGainDb: data.plan.song_a_gain_db,
      songBGainDb: data.plan.song_b_gain_db,
      crossfadeBias: data.plan.crossfade_bias,
      songBTempoMultiplier: data.plan.song_b_tempo_multiplier,
    },
    effectiveSongBBpm: data.effective_song_b_bpm,
    tempoCompatibility: data.tempo_compatibility,
    usedTempoNormalization: data.used_tempo_normalization,
    songAAnchorSource: data.song_a_anchor_source,
    songBAnchorSource: data.song_b_anchor_source,
  };
}

async function extractErrorDetail(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (
      typeof data === "object" &&
      data !== null &&
      "detail" in data &&
      typeof data.detail === "string"
    ) {
      return data.detail;
    }
  } catch {
    // Response body wasn't JSON (or was empty); fall through.
  }
  return "Analysis failed.";
}
