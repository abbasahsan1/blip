/**
 * useAudioPrefetch  (§6.4 — Speculative Audio Prefetching)
 *
 * Asynchronously downloads the next 2–3 upcoming audio variants into the
 * local device cache using expo-file-system so they are available for
 * instantaneous (<500ms) playback when the user swipes to them.
 *
 * Bitrate selection heuristic:
 *   - Use `low` variant if: screen is off AND Bluetooth is connected without
 *     active Wi-Fi (metered/background audio scenario).
 *   - Otherwise use `standard` variant.
 *
 * When a pre-cached URI is available, callers pass it to useAudioPlayer as
 * `localUri`, which it prefers over the remote URL, ensuring instantaneous
 * first-byte latency.
 */

import { useCallback, useEffect, useRef } from 'react';
import * as FileSystem from 'expo-file-system';
import { AppState, type AppStateStatus, Platform } from 'react-native';
import { resolvePublicAudioUrl } from '@/lib/api';
import { getDeviceSignal } from '@/lib/deviceSignal';
import type { Blipp } from '@/lib/types';

// §6.4: Asynchronously download the next 2 to 3 upcoming audio variants
const PREFETCH_AHEAD_COUNT = 3;

// ─── Global Prefetch Memory Cache ─────────────────────────────────────────────
// Shared across all AudioReel instances so any card can retrieve cached files synchronously.
const globalCacheMap = new Map<string, string>();
const globalAttemptedSet = new Set<string>();
const globalInflightMap = new Map<string, FileSystem.DownloadResumable>();

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Selects the appropriate audio variant URL based on heuristic:
 * - Low tier if screen is off and Bluetooth is connected without active Wi-Fi
 * - Standard tier otherwise
 */
export function selectBitrateUrl(item: Blipp): string {
  const signal = getDeviceSignal(false);
  const appState: AppStateStatus = AppState.currentState;
  const isWeb = Platform.OS === 'web' && typeof document !== 'undefined';
  const isScreenOff =
    (isWeb && (document.hidden || document.visibilityState === 'hidden')) ||
    appState !== 'active';

  // Best-effort Wi-Fi detection via Network Information API (web)
  let isWifi = true;
  if (
    typeof navigator !== 'undefined' &&
    'connection' in navigator &&
    (navigator as any).connection?.type
  ) {
    isWifi = (navigator as any).connection.type === 'wifi';
  }

  // §6.4: use low tier if screen is off and Bluetooth is connected without active Wi-Fi; otherwise standard
  const isBluetooth = signal === 'bluetooth_connected';
  const useLow = isScreenOff && isBluetooth && !isWifi;

  const raw = useLow
    ? (item.audio_variants?.low ||
       item.audio_variants?.standard ||
       item.audio_url)
    : (item.audio_variants?.standard || item.audio_url);

  return resolvePublicAudioUrl(raw) || '';
}

/** Stable local cache path for a given blippId. */
export function toCachePath(blippId: string): string {
  const dir = FileSystem.cacheDirectory ?? '';
  return `${dir}blipp_${blippId}.mp3`;
}

// ─── Public surface ───────────────────────────────────────────────────────────

export interface UseAudioPrefetchOptions {
  items: Blipp[];
  activeIndex: number;
  enabled?: boolean;
}

export interface UseAudioPrefetchResult {
  /**
   * Returns the local file:// URI for a cached blipp, or null if not yet downloaded.
   * Pass the returned URI to useAudioPlayer as `localUri`.
   */
  getCachedUri: (blippId: string) => string | null;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAudioPrefetch({
  items,
  activeIndex,
  enabled = true,
}: UseAudioPrefetchOptions): UseAudioPrefetchResult {
  const itemsRef = useRef(items);
  itemsRef.current = items;

  // Guard: expo-file-system availability
  const fsAvailable =
    Platform.OS !== 'web' ||
    (typeof FileSystem.cacheDirectory === 'string' && FileSystem.cacheDirectory !== '');

  const prefetchItem = useCallback(
    async (item: Blipp) => {
      if (!fsAvailable) return;

      const blippId = item.blipp_id || item.id;
      if (!blippId) return;

      // De-duplicate: skip if already cached, attempted, or in-flight
      if (globalCacheMap.has(blippId)) return;
      if (globalAttemptedSet.has(blippId)) return;
      if (globalInflightMap.has(blippId)) return;

      globalAttemptedSet.add(blippId);

      const remoteUrl = selectBitrateUrl(item);
      if (!remoteUrl) return;

      const localPath = toCachePath(blippId);

      // ── Disk cache check ───────────────────────────────────────────────────
      try {
        const info = await FileSystem.getInfoAsync(localPath);
        if (info.exists) {
          globalCacheMap.set(blippId, info.uri);
          return;
        }
      } catch {
        // Fall through to download if getInfoAsync fails
      }

      // ── Speculative download ───────────────────────────────────────────────
      const downloadResumable = FileSystem.createDownloadResumable(
        remoteUrl,
        localPath,
        {},
      );
      globalInflightMap.set(blippId, downloadResumable);

      try {
        const result = await downloadResumable.downloadAsync();
        if (result?.uri) {
          globalCacheMap.set(blippId, result.uri);
        }
      } catch {
        // Prefetch errors are transparent; playback falls back to remote streaming
      } finally {
        globalInflightMap.delete(blippId);
      }
    },
    [fsAvailable],
  );

  // ── Trigger prefetch for the next 2–3 items when active ────────────────────
  useEffect(() => {
    if (!enabled || !items.length) return;

    for (let offset = 1; offset <= PREFETCH_AHEAD_COUNT; offset++) {
      const nextItem = items[activeIndex + offset];
      if (nextItem) {
        prefetchItem(nextItem);
      }
    }
  }, [activeIndex, items, enabled, prefetchItem]);

  // ── Query local URI synchronously ──────────────────────────────────────────
  const getCachedUri = useCallback((blippId: string): string | null => {
    if (!blippId) return null;
    return globalCacheMap.get(blippId) ?? null;
  }, []);

  return { getCachedUri };
}
