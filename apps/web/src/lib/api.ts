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
