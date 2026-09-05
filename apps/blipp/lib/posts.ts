import type { Blipp, AudioPost } from './types';

export type { Blipp, AudioPost };

/**
 * Clean domain post utilities without synthetic mocks or local storage blobs.
 */
export function isAudioPlayable(blipp: Blipp): boolean {
  const uri = blipp.audio_variants?.standard || blipp.audio_url || blipp.audioUrl;
  return Boolean(uri && uri.trim().length > 0);
}
