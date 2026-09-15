const AUDIO_EXTENSION_PATTERN =
  /\.(mp3|wav|wave|ogg|oga|opus|m4a|aac|flac|webm|weba)$/i;

export function isSupportedAudioFile(file: File): boolean {
  if (file.type.startsWith("audio/")) return true;
  return AUDIO_EXTENSION_PATTERN.test(file.name);
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const totalSeconds = Math.round(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

/** Millisecond-precision timestamp (e.g. "1:43.482") for beat anchors. */
export function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00.000";
  const totalMs = Math.round(seconds * 1000);
  const minutes = Math.floor(totalMs / 60000);
  const remainingMs = totalMs % 60000;
  const wholeSeconds = Math.floor(remainingMs / 1000);
  const milliseconds = remainingMs % 1000;
  return `${minutes}:${wholeSeconds.toString().padStart(2, "0")}.${milliseconds
    .toString()
    .padStart(3, "0")}`;
}
