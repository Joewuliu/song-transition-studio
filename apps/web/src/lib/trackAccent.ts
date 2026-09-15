export type TrackAccent = "violet" | "teal";

interface AccentStyle {
  chip: string;
  wave: string;
  progress: string;
  ring: string;
  text: string;
}

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
