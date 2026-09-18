"use client";

import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

interface UseWaveSurferOptions {
  file: File;
  waveColor: string;
  progressColor: string;
  /** Pixel height of the rendered waveform; defaults to 96 (the compact
   * setup-page size) — callers wanting a larger, deck-style waveform can
   * pass a bigger value without affecting other call sites. */
  height?: number;
  /** Called with the clicked/dragged-to time whenever the user seeks. */
  onSeek?: (timeSeconds: number) => void;
}

interface UseWaveSurferResult {
  containerRef: (element: HTMLDivElement | null) => void;
  isReady: boolean;
  isPlaying: boolean;
  duration: number;
  /** Current playback position, in seconds — the same underlying
   * WaveSurfer instance's own position (via its "timeupdate" event),
   * never a second, independently-tracked playback clock. */
  currentTime: number;
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
  height = 96,
  onSeek,
}: UseWaveSurferOptions): UseWaveSurferResult {
  const wavesurferRef = useRef<WaveSurfer | null>(null);
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Kept in a ref (rather than a WaveSurfer-effect dependency) so a new
  // `onSeek` reference from the caller never tears down and recreates the
  // WaveSurfer instance — only the callback's *target* changes.
  const onSeekRef = useRef(onSeek);
  useEffect(() => {
    onSeekRef.current = onSeek;
  }, [onSeek]);

  useEffect(() => {
    if (!container) return;

    const url = URL.createObjectURL(file);
    const wavesurfer = WaveSurfer.create({
      container,
      url,
      waveColor,
      progressColor,
      cursorColor: progressColor,
      height,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      cursorWidth: 1,
      normalize: true,
    });
    wavesurferRef.current = wavesurfer;

    const handleReady = (readyDuration: number) => {
      setDuration(readyDuration);
      setCurrentTime(0);
      setIsReady(true);
    };
    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);
    const handleFinish = () => setIsPlaying(false);
    const handleError = () => {
      setError("This file couldn't be loaded as audio.");
      setIsReady(false);
    };
    const handleInteraction = (newTime: number) => {
      onSeekRef.current?.(newTime);
    };
    // Fires continuously during playback and immediately after a seek —
    // the same single source of truth for "where is playback right now"
    // that WaveSurfer's own cursor already reflects visually.
    const handleTimeUpdate = (time: number) => setCurrentTime(time);

    wavesurfer.on("ready", handleReady);
    wavesurfer.on("play", handlePlay);
    wavesurfer.on("pause", handlePause);
    wavesurfer.on("finish", handleFinish);
    wavesurfer.on("error", handleError);
    wavesurfer.on("interaction", handleInteraction);
    wavesurfer.on("timeupdate", handleTimeUpdate);

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
  }, [container, file, waveColor, progressColor, height]);

  const togglePlay = () => {
    void wavesurferRef.current?.playPause();
  };

  return {
    containerRef: setContainer,
    isReady,
    isPlaying,
    duration,
    currentTime,
    error,
    togglePlay,
  };
}
