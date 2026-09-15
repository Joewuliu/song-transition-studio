"use client";

import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

interface UseWaveSurferOptions {
  file: File;
  waveColor: string;
  progressColor: string;
}

interface UseWaveSurferResult {
  containerRef: (element: HTMLDivElement | null) => void;
  isReady: boolean;
  isPlaying: boolean;
  duration: number;
  error: string | null;
  togglePlay: () => void;
}

/**
 * Mount this hook under a component keyed by a stable per-track identity
 * (e.g. a selection id, not `file` itself) so a new track always starts
 * from fresh, correctly initialized state instead of needing manual resets
 * inside the effect.
 *
 * The object URL for `file` is created and revoked entirely within this
 * effect: it's only ever needed to hand to WaveSurfer, so it never needs to
 * exist as React state.
 */
export function useWaveSurfer({
  file,
  waveColor,
  progressColor,
}: UseWaveSurferOptions): UseWaveSurferResult {
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!container) return;

    const url = URL.createObjectURL(file);
    const wavesurfer = WaveSurfer.create({
      container,
      url,
      waveColor,
      progressColor,
      cursorColor: progressColor,
      height: 96,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      cursorWidth: 1,
      normalize: true,
    });
    wavesurferRef.current = wavesurfer;

    const handleReady = (readyDuration: number) => {
      setDuration(readyDuration);
      setIsReady(true);
    };
    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);
    const handleFinish = () => setIsPlaying(false);
    const handleError = () => {
      setError("This file couldn't be loaded as audio.");
      setIsReady(false);
    };

    wavesurfer.on("ready", handleReady);
    wavesurfer.on("play", handlePlay);
    wavesurfer.on("pause", handlePause);
    wavesurfer.on("finish", handleFinish);
    wavesurfer.on("error", handleError);

    return () => {
      wavesurfer.unAll();
      try {
        wavesurfer.destroy();
      } catch {
        // WaveSurfer can throw if torn down mid-decode; nothing further to clean up.
      }
      wavesurferRef.current = null;
      URL.revokeObjectURL(url);
    };
  }, [container, file, waveColor, progressColor]);

  const togglePlay = () => {
    void wavesurferRef.current?.playPause();
  };

  return { containerRef: setContainer, isReady, isPlaying, duration, error, togglePlay };
}
