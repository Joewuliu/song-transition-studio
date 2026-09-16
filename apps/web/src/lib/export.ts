import { AUDIO_EXTENSION_PATTERN } from "@/lib/audio";

const SEGMENT_MAX_LENGTH = 60;
const FILENAME_MAX_LENGTH = 150;
const DEFAULT_BASENAME = "transition";

/** Lowercase, hyphen-separated, filesystem-safe. Collapses any run of
 * whitespace/punctuation/unicode into a single "-" and trims stray
 * leading/trailing hyphens — used identically for the auto-generated
 * default filename and for sanitizing a user-edited one, so both are
 * always safe to write to disk on any OS. */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9-_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * A useful default export filename derived from the two source
 * filenames, e.g. "midnight-city-to-something-about-us-transition.wav".
 * Falls back to "song-a"/"song-b" for a name that sanitizes to nothing
 * (e.g. a file named only in symbols), so the result is never empty.
 */
export function defaultExportFilename(
  songAFilename: string,
  songBFilename: string,
): string {
  const songASlug =
    slugify(songAFilename.replace(AUDIO_EXTENSION_PATTERN, "")).slice(
      0,
      SEGMENT_MAX_LENGTH,
    ) || "song-a";
  const songBSlug =
    slugify(songBFilename.replace(AUDIO_EXTENSION_PATTERN, "")).slice(
      0,
      SEGMENT_MAX_LENGTH,
    ) || "song-b";
  return sanitizeExportFilename(`${songASlug}-to-${songBSlug}-transition`);
}

/**
 * Normalizes any user-edited (or auto-generated) filename into a safe
 * ".wav" filename: strips a trailing ".wav" before re-slugifying (so
 * re-sanitizing an already-sanitized name is a no-op), guarantees a
 * non-empty base name, and always re-appends exactly one ".wav" — so the
 * user can never accidentally export a file with no extension, the wrong
 * extension, or filesystem-hostile characters, no matter what they typed.
 */
export function sanitizeExportFilename(input: string): string {
  const withoutExtension = input.replace(/\.wav$/i, "");
  const slug = slugify(withoutExtension);
  const base = (slug || DEFAULT_BASENAME).slice(0, FILENAME_MAX_LENGTH);
  return `${base}.wav`;
}

/**
 * Triggers a browser download of `file` as `filename` without ever
 * uploading it anywhere or retaining the object URL: a temporary URL and
 * anchor are created, clicked, and torn down immediately, and the URL is
 * revoked shortly after (deferred slightly so the browser has actually
 * started the download first — revoking synchronously can cancel it in
 * some browsers).
 */
export function downloadTransition(file: File, filename: string): void {
  const url = URL.createObjectURL(file);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
