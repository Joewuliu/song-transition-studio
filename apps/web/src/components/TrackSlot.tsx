"use client";

import {
  useCallback,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import { LoadedTrack } from "@/components/LoadedTrack";
import { UploadIcon } from "@/components/icons";
import { isSupportedAudioFile } from "@/lib/audio";
import { ACCENT_STYLES, type TrackAccent } from "@/lib/trackAccent";
import type { TrackAnalysis } from "@/lib/api";
import type { BeatAnchor } from "@/lib/transitionPlan";

export type { TrackAccent };

interface TrackSlotProps {
  label: string;
  accent: TrackAccent;
  file: File | null;
  onFileChange: (file: File | null) => void;
  onAnalysisChange: (analysis: TrackAnalysis | null) => void;
  anchor: BeatAnchor | null;
  onAnchorChange: (anchor: BeatAnchor | null) => void;
}

export function TrackSlot({
  label,
  accent,
  file,
  onFileChange,
  onAnalysisChange,
  anchor,
  onAnchorChange,
}: TrackSlotProps) {
  const [fileError, setFileError] = useState<string | null>(null);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  // Purely a local remount key for LoadedTrack (so its internal waveform/
  // analysis state always starts fresh on replace) — `file` itself is now
  // owned by the parent, so this never needs to leave this component. Must
  // be state (not a ref) since it's read during render as a `key`.
  const [selectionKey, setSelectionKey] = useState(0);

  const styles = ACCENT_STYLES[accent];

  const applyFile = useCallback(
    (candidate: File) => {
      if (!isSupportedAudioFile(candidate)) {
        setFileError(`"${candidate.name}" isn't a supported audio file.`);
        return;
      }
      setFileError(null);
      setSelectionKey((key) => key + 1);
      onFileChange(candidate);
      onAnalysisChange(null);
      onAnchorChange(null);
    },
    [onFileChange, onAnalysisChange, onAnchorChange],
  );

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const candidate = event.target.files?.[0];
    event.target.value = "";
    if (candidate) applyFile(candidate);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current = 0;
    setIsDraggingOver(false);
    const candidate = event.dataTransfer.files?.[0];
    if (candidate) applyFile(candidate);
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
  };

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current += 1;
    setIsDraggingOver(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setIsDraggingOver(false);
    }
  };

  const handleRemove = () => {
    setFileError(null);
    onFileChange(null);
    onAnalysisChange(null);
    onAnchorChange(null);
  };

  const openFileDialog = () => inputRef.current?.click();

  return (
    <section className="flex flex-col gap-3">
      <span
        className={`w-fit rounded-full px-2.5 py-1 text-xs font-medium ${styles.chip}`}
      >
        {label}
      </span>

      <input
        ref={inputRef}
        type="file"
        accept="audio/*"
        className="hidden"
        onChange={handleInputChange}
      />

      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        className={`rounded-xl border transition-colors ${
          isDraggingOver
            ? `border-transparent bg-zinc-50 ring-2 ${styles.ring} dark:bg-zinc-900`
            : "border-zinc-200 dark:border-zinc-800"
        }`}
      >
        {!file ? (
          <button
            type="button"
            onClick={openFileDialog}
            className="flex h-32 w-full flex-col items-center justify-center gap-2 text-sm text-zinc-400 transition-colors hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300"
          >
            <UploadIcon className="h-5 w-5" />
            <span>Drop an audio file, or click to browse</span>
          </button>
        ) : (
          <LoadedTrack
            key={selectionKey}
            file={file}
            waveColor={styles.wave}
            progressColor={styles.progress}
            onAnalysisChange={onAnalysisChange}
            anchor={anchor}
            onAnchorChange={onAnchorChange}
            onReplace={openFileDialog}
            onRemove={handleRemove}
          />
        )}
      </div>

      {fileError && <p className="text-xs text-red-500">{fileError}</p>}
    </section>
  );
}
