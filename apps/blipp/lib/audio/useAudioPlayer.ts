/**
 * useAudioPlayer
 *
 * Encapsulates the Web Audio element lifecycle for Blipp audio playback.
 * Uses the browser's native Audio API (not expo-av) since the app deploys
 * as an Expo Web app.
 *
 * Responsibilities:
 *   - Encapsulate Audio lifecycle: loading, buffering, unloading, play, pause, seek, and error states
 *   - Active position tracking (positionSeconds, durationSeconds, progress)
 *   - Variant selection: defaults to item.audio_variants?.standard || item.audio_url
 *   - Clean controls: { isPlaying, positionSeconds, durationSeconds, isLoading, togglePlayPause, seekTo }
 *   - Ensure previous sound instances are cleanly unloaded from memory when navigating or unmounting
 *   - Accept a pre-cached localUri from useAudioPrefetch for <500ms first-byte start latency
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Animated } from 'react-native';
import { resolveMediaUrl, resolvePublicAudioUrl } from '@/lib/api';
import { resetPlaybackSessionId } from '@/lib/audio/listenTracker';
import type { Blipp } from '@/lib/types';

// ─── Public surface ───────────────────────────────────────────────────────────

export type AudioState = 'idle' | 'loading' | 'ready' | 'playing' | 'paused' | 'seeking' | 'ended' | 'error';

export interface AudioPlayerControls {
  /** The explicit lifecycle state of the audio element */
  audioState: AudioState;
  /** Whether audio is currently playing (not paused, not ended). */
  isPlaying: boolean;
  /** True while the browser is buffering / waiting for data. */
  isLoading: boolean;
  /** Current playback position in whole seconds. */
  positionSeconds: number;
  /** Total track duration in whole seconds (0 until metadata loads). */
  durationSeconds: number;
  /** Playback progress as an Animated.Value (for native waveform / progress bar rendering without React re-renders). */
  progress: Animated.Value;
  /** Toggle between play and pause. No-ops if no audio is loaded. */
  togglePlayPause: () => void;
  /** Seek to an absolute position in seconds. */
  seekTo: (seconds: number) => void;
  /** True when a sponsored slot has an unreachable or *.internal audio URL. */
  isAdFallback: boolean;
  /** 5-second countdown timer for sponsored promo fallback. */
  adCountdown: number;
}

export interface UseAudioPlayerOptions {
  /** The Blipp item to play. Hook re-initialises whenever this changes. */
  item: Blipp | undefined;
  /**
   * Whether this reel is the currently visible / active slide.
   * Transitioning from true → false pauses audio playback.
   */
  isActive: boolean;
  /**
   * Optional pre-cached local file URI from useAudioPrefetch.
   * When provided it overrides the remote URL, enabling instant load.
   */
  localUri?: string | null;
  /**
   * Only true for active or immediately adjacent items to prevent eager network fetches.
   */
  shouldLoad?: boolean;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAudioPlayer({
  item,
  isActive,
  localUri,
  shouldLoad = true,
}: UseAudioPlayerOptions): AudioPlayerControls {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [audioState, setAudioState] = useState<AudioState>('idle');
  const [positionSeconds, setPositionSeconds] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const progressAnim = useRef(new Animated.Value(0)).current;

  const isPlaying = audioState === 'playing';
  const isLoading = audioState === 'loading';

  // Variant selection: default to item.audio_variants?.standard || item.audio_url
  const remoteUrl = resolveMediaUrl(
    item?.audio_variants?.standard || item?.audio_url,
  );
  // Pre-cached local file URI overrides remote URL for <500ms first-byte latency (§6.4)
  const audioUri = localUri || remoteUrl;

  // ── Sponsored Ad Resilience (§6.4) ──────────────────────────────────────────
  const isAd = Boolean(item?.is_ad || item?.is_sponsored);
  const rawAudioUrl = item?.audio_variants?.standard || item?.audio_url || '';
  const isInternalUrl = Boolean(rawAudioUrl && (rawAudioUrl.includes('.internal') || rawAudioUrl.includes('cdn.blipps.internal')));

  const [isAdFallback, setIsAdFallback] = useState(false);
  const [adCountdown, setAdCountdown] = useState(5);

  useEffect(() => {
    if (isAd && isInternalUrl) {
      setIsAdFallback(true);
      setAudioState('idle');
    } else {
      setIsAdFallback(false);
      setAdCountdown(5);
    }
  }, [isAd, isInternalUrl, item?.blipp_id, item?.id]);

  useEffect(() => {
    if (!isAdFallback || !isActive) return;
    setAdCountdown(5);
    const timer = setInterval(() => {
      setAdCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [isAdFallback, isActive]);

  // ── Audio element lifecycle ─────────────────────────────────────────────────
  useEffect(() => {
    // Guard: If ad fallback is active or Web Audio API is unavailable, do not attempt to load audio
    if (isAd && isInternalUrl) return;
    if (typeof window === 'undefined' || typeof Audio === 'undefined') return;
    if (!audioUri) return;
    if (!shouldLoad) return;

    // Clean up any existing audio element before instantiating a new one
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
      try {
        audioRef.current.load();
      } catch {
        // Safe fallback
      }
      audioRef.current = null;
    }

    // New track → new playback session for telemetry correlation
    resetPlaybackSessionId();

    const audio = new Audio(audioUri);
    audioRef.current = audio;

    // Reset state for new track
    setAudioState('loading');
    setPositionSeconds(0);
    setDurationSeconds(0);
    progressAnim.setValue(0);

    // ── Event handlers ────────────────────────────────────────────────────────

    const handleCanPlay = () => setAudioState(prev => prev === 'playing' ? 'playing' : 'ready');
    const handleWaiting = () => setAudioState('loading');

    const handlePlaying = () => {
      setAudioState('playing');
    };

    const handlePause = () => {
      // Don't override 'ended' or 'seeking' if they just fired
      setAudioState(prev => prev === 'ended' || prev === 'seeking' ? prev : 'paused');
    };

    const handleSeeking = () => setAudioState('seeking');
    const handleSeeked = () => setAudioState(prev => audioRef.current && !audioRef.current.paused ? 'playing' : 'ready');

    const handleTimeUpdate = () => {
      const dur = audio.duration && isFinite(audio.duration) ? audio.duration : 0;
      const pos = audio.currentTime ?? 0;
      const frac = dur > 0 ? pos / dur : 0;
      
      const posInt = Math.floor(pos);
      const durInt = Math.floor(dur);
      
      setPositionSeconds(prev => prev === posInt ? prev : posInt);
      setDurationSeconds(prev => prev === durInt ? prev : durInt);
      progressAnim.setValue(frac);
    };

    const handleEnded = () => {
      setAudioState('ended');
      progressAnim.setValue(1);
      setTimeout(() => {
        progressAnim.setValue(0);
        setPositionSeconds(0);
      }, 400);
    };

    const handleError = () => {
      setAudioState('error');
      console.warn('[useAudioPlayer] Audio load error for URI:', audioUri);
      if (isAd) {
        setIsAdFallback(true);
      }
    };

    audio.addEventListener('canplay', handleCanPlay);
    audio.addEventListener('waiting', handleWaiting);
    audio.addEventListener('playing', handlePlaying);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('seeking', handleSeeking);
    audio.addEventListener('seeked', handleSeeked);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('error', handleError);

    return () => {
      audio.pause();
      audio.removeEventListener('canplay', handleCanPlay);
      audio.removeEventListener('waiting', handleWaiting);
      audio.removeEventListener('playing', handlePlaying);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('seeking', handleSeeking);
      audio.removeEventListener('seeked', handleSeeked);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('error', handleError);
      // Cleanly unload from memory
      audio.src = '';
      try {
        audio.load();
      } catch {
        // Safe fallback
      }
      audioRef.current = null;
    };
  // Re-run whenever the resolved URI changes (item switch or cache hit arrives)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUri, item?.blipp_id, item?.id, isAd, isInternalUrl, shouldLoad]);

  // ── Handle Play/Pause when navigating between reels ─────────────────────────
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (!isActive && !audio.paused) {
      audio.pause();
    } else if (isActive && audio.paused) {
      audio.play().catch((err) => {
        // Autoplay may be blocked by browser policy until first interaction
        console.warn('[useAudioPlayer] Auto-play blocked or rejected:', err);
      });
    }
  }, [isActive]);

  // ── Controls ────────────────────────────────────────────────────────────────

  const togglePlayPause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (audio.paused) {
      audio.play().catch((err) => {
        console.warn('[useAudioPlayer] play() rejected:', err);
      });
    } else {
      audio.pause();
    }
  }, []);

  const seekTo = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, seconds);
  }, []);

  return {
    audioState,
    isPlaying,
    isLoading,
    positionSeconds,
    durationSeconds,
    progress: progressAnim,
    togglePlayPause,
    seekTo,
    isAdFallback,
    adCountdown,
  };
}
