import type { BeatAnchor } from "@/lib/transitionPlan";

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

export interface TrackAnalysis {
  durationSeconds: number;
  tempoBpm: number;
  beatCount: number;
  beats: number[];
}

interface TrackAnalysisResponse {
  duration_seconds: number;
  tempo_bpm: number;
  beat_count: number;
  beats: number[];
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
  };
}

export interface RenderTransitionParams {
  songAFile: File;
  songBFile: File;
  songAAnchor: BeatAnchor;
  songBAnchor: BeatAnchor;
  songABpm: number;
  songBBpm: number;
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

const RENDER_TRANSITION_BEATS = 16;

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
      transition_beats: RENDER_TRANSITION_BEATS,
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
