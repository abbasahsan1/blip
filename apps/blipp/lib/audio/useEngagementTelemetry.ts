/**
 * useEngagementTelemetry
 *
 * Manages playback telemetry dispatch per Sections 6.4 & 6.5.
 * Wraps `recordPlayProgress` from listenTracker.ts and device signal context
 * from deviceSignal.ts into a structured React lifecycle hook.
 *
 * Responsibilities:
 *   - Manage the ~5-second periodic telemetry timer while playback is active
 *   - Capture active device context ('screen_on' | 'screen_off' | 'bluetooth_connected' | 'app_backgrounded')
 *   - Dispatch batched 'play_progress' events to POST /v1/events via centralized API client
 *   - Dispatch terminal playback events:
 *       * 'play_complete' when position reaches >= 90% of duration
 *       * 'skip' when user navigates away (isActive: true -> false) before reaching threshold
 */

import { useEffect, useRef } from 'react';
import { recordPlayProgress } from '@/lib/audio/listenTracker';
import type { Blipp } from '@/lib/types';

// Section 6.5: emit one play_progress event every 5 seconds of active playback.
const TELEMETRY_INTERVAL_MS = 5_000;
// Section 6.5: completion threshold is 90% of total duration.
const COMPLETION_THRESHOLD_RATIO = 0.9;

export interface UseEngagementTelemetryOptions {
  /** The currently active Blipp item. */
  item: Blipp | undefined;
  /** Live playback state from useAudioPlayer. */
  isPlaying: boolean;
  /** Current position in seconds (updated continuously by useAudioPlayer). */
  positionSeconds: number;
  /** Total duration in seconds. */
  durationSeconds: number;
  /** Whether the reel is the currently active/visible card. */
  isActive?: boolean;
}

export function useEngagementTelemetry({
  item,
  isPlaying,
  positionSeconds,
  durationSeconds,
  isActive = true,
}: UseEngagementTelemetryOptions): void {
  const blippId = item?.blipp_id || item?.id;

  // Refs for current values so timers & lifecycle hooks always read latest data
  // without needing to recreate intervals on every timeupdate tick.
  const positionRef = useRef(positionSeconds);
  const durationRef = useRef(durationSeconds);
  const isPlayingRef = useRef(isPlaying);
  const isActiveRef = useRef(isActive);

  // State flags for terminal event dispatching
  const hasCompletedRef = useRef(false);
  const hasStartedRef = useRef(false);
  const prevIsActiveRef = useRef(isActive);
  const currentBlippIdRef = useRef<string | undefined>(blippId);

  // Keep refs in sync on every render
  useEffect(() => { positionRef.current = positionSeconds; });
  useEffect(() => { durationRef.current = durationSeconds; });
  useEffect(() => { isPlayingRef.current = isPlaying; });
  useEffect(() => { isActiveRef.current = isActive; });

  // Reset tracking state whenever the track / blippId changes
  useEffect(() => {
    if (currentBlippIdRef.current !== blippId) {
      currentBlippIdRef.current = blippId;
      hasCompletedRef.current = false;
      hasStartedRef.current = false;
      prevIsActiveRef.current = isActive;
    }
  }, [blippId, isActive]);

  // ── Terminal Event: play_complete (position >= 90% of duration) ────────────
  useEffect(() => {
    if (!blippId || hasCompletedRef.current) return;

    const dur =
      durationSeconds > 0
        ? durationSeconds
        : (item?.duration_seconds ?? item?.duration ?? 0);

    if (dur > 0 && positionSeconds >= Math.floor(dur * COMPLETION_THRESHOLD_RATIO)) {
      hasCompletedRef.current = true;
      recordPlayProgress({
        blipp_id: blippId,
        position_seconds: positionSeconds,
        duration_seconds: dur,
        event_type: 'play_complete',
      });
    }
  }, [positionSeconds, durationSeconds, blippId, item?.duration_seconds, item?.duration]);

  // ── Terminal Event: skip (navigating away before 90% completion threshold) ──
  useEffect(() => {
    const wasActive = prevIsActiveRef.current;
    prevIsActiveRef.current = isActive;

    if (wasActive && !isActive && blippId) {
      // User navigated away from this card
      const dur =
        durationRef.current > 0
          ? durationRef.current
          : (item?.duration_seconds ?? item?.duration ?? 0);
      const pos = positionRef.current;

      // Only emit skip if track was ever played and hasn't reached completion
      const reachedCompletion = dur > 0 && pos >= dur * COMPLETION_THRESHOLD_RATIO;
      if (!hasCompletedRef.current && !reachedCompletion && (hasStartedRef.current || pos > 0)) {
        recordPlayProgress({
          blipp_id: blippId,
          position_seconds: pos,
          duration_seconds: dur,
          event_type: 'skip',
        });
      }
    }
  }, [isActive, blippId, item?.duration_seconds, item?.duration]);

  // ── Periodic ~5s telemetry timer during active playback ─────────────────────
  useEffect(() => {
    if (!isPlaying || !blippId) return;

    hasStartedRef.current = true;

    // Emit initial play_progress on playback start
    recordPlayProgress({
      blipp_id: blippId,
      position_seconds: positionRef.current,
      duration_seconds: durationRef.current,
      event_type: 'play_progress',
    });

    const timer = setInterval(() => {
      recordPlayProgress({
        blipp_id: blippId,
        position_seconds: positionRef.current,
        duration_seconds: durationRef.current,
        event_type: 'play_progress',
      });
    }, TELEMETRY_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [isPlaying, blippId]);
}
