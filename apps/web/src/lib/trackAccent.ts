export type TrackAccent = "violet" | "teal";

interface AccentStyle {
  chip: string;
  wave: string;
  progress: string;
  ring: string;
  text: string;
}

interface EditorTrackStyle {
  /** CSS color used for identity fills (slider fill, playing transport). */
  color: string;
  /** Tailwind text-color class for labels and readouts. */
  textClass: string;
  /** Unplayed and played waveform colors, tuned for the dark editor. */
  wave: string;
  progress: string;
}

/** Song identities on the dark editor surface: violet = Song A, teal = Song B. */
export const EDITOR_TRACK_STYLES: Record<TrackAccent, EditorTrackStyle> = {
  violet: {
    color: "var(--ed-violet)",
    textClass: "text-ed-violet",
    wave: "#8f78ee",
    progress: "#d9ceff",
  },
  teal: {
    color: "var(--ed-teal)",
    textClass: "text-ed-teal",
    wave: "#2bbfad",
    progress: "#a7f3e6",
  },
};

export const ACCENT_STYLES: Record<TrackAccent, AccentStyle> = {
  violet: {
    chip: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    wave: "#c4b5fd",
    progress: "#7c3aed",
    ring: "ring-violet-400",
    text: "text-violet-600 dark:text-violet-400",
  },
  teal: {
    chip: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
    wave: "#5eead4",
    progress: "#0d9488",
    ring: "ring-teal-400",
    text: "text-teal-600 dark:text-teal-400",
  },
};
