import { api } from '../api';
import { useSessionStore } from '../store/sessionStore';
import { computeDeviceSignal } from '../deviceSignal';

export interface PlayProgressEvent {
  event_type: 'play_progress' | 'play_complete' | 'skip';
  user_id: string;
  blipp_id: string;
  session_id: string;
  position_seconds: number;
  duration_seconds: number;
  device_signal: 'screen_on' | 'screen_off' | 'bluetooth_connected' | 'app_backgrounded';
  timestamp: string;
}

let activeSessionId: string = '';

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function getPlaybackSessionId(): string {
  if (!activeSessionId) {
    activeSessionId = generateUUID();
  }
  return activeSessionId;
}

export function resetPlaybackSessionId(): string {
  activeSessionId = generateUUID();
  return activeSessionId;
}

/**
 * Resolves high-fidelity device telemetry signal:
 * - 'app_backgrounded' when AppState is background
 * - 'screen_off' when audio playing while screen is locked/hidden
 * - 'bluetooth_connected' when audio is routed to external device
 * - 'screen_on' when screen is foregrounded & active
 */
export function getActiveDeviceSignal(isPlaying: boolean = true): PlayProgressEvent['device_signal'] {
  const signal = computeDeviceSignal(isPlaying);
  if (
    signal === 'screen_off' ||
    signal === 'bluetooth_connected' ||
    signal === 'app_backgrounded'
  ) {
    return signal;
  }
  return 'screen_on';
}

/**
 * Emits real playback telemetry payload to POST /v1/events.
 * Eliminates synthetic disconnected local loops.
 */
export async function recordPlayProgress(params: {
  blipp_id: string;
  position_seconds: number;
  duration_seconds: number;
  event_type?: PlayProgressEvent['event_type'];
  user_id?: string;
  session_id?: string;
}): Promise<void> {
  const sessionUser = useSessionStore.getState().user;
  const userId = params.user_id || sessionUser?.id;
  if (!userId) {
    // Strictly require authenticated user; do not emit telemetry with dummy fallback UUIDs
    return;
  }
  const sessionId = params.session_id || getPlaybackSessionId();
  const deviceSignal = getActiveDeviceSignal(true);

  const payload: PlayProgressEvent = {
    event_type: params.event_type || 'play_progress',
    user_id: userId,
    blipp_id: params.blipp_id,
    session_id: sessionId,
    position_seconds: Math.max(0, Math.round(params.position_seconds)),
    duration_seconds: Math.max(0, Math.round(params.duration_seconds)),
    device_signal: deviceSignal,
    timestamp: new Date().toISOString(),
  };

  try {
    await api.post('/v1/events', payload);
  } catch {
    // Non-blocking telemetry delivery
  }
}
