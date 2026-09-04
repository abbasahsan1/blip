import { AppState, type AppStateStatus, Platform } from 'react-native';
import type { DeviceSignal } from './types';

/**
 * High-fidelity device signal tracking (§5.8).
 * Tracks screen states, backgrounding, and external Bluetooth/headphone audio routing.
 * Accurately reports: 'screen_on' | 'screen_off' | 'bluetooth_connected' | 'app_backgrounded'.
 */

let isBluetoothConnected = false;
let currentSignal: DeviceSignal = 'screen_on';
const listeners = new Set<(signal: DeviceSignal) => void>();

// Continuously inspect audio output routes for Bluetooth or external devices
async function updateAudioOutputRoute() {
  if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.mediaDevices?.enumerateDevices) {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const bluetoothDevice = devices.find((device) => {
        const label = (device.label || '').toLowerCase();
        return (
          device.kind === 'audiooutput' &&
          (label.includes('bluetooth') ||
            label.includes('airpods') ||
            label.includes('wireless') ||
            label.includes('headphone') ||
            label.includes('headset') ||
            label.includes('hands-free') ||
            label.includes('buds'))
        );
      });
      isBluetoothConnected = Boolean(bluetoothDevice);
    } catch {
      // MediaDevices permission or enumeration restricted
    }
  }
}

// Initialize audio device listener
if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.mediaDevices) {
  updateAudioOutputRoute();
  navigator.mediaDevices.addEventListener?.('devicechange', () => {
    updateAudioOutputRoute().then(() => notifySignalChange());
  });
}

/**
 * Computes the active device signal given the current app state, screen visibility,
 * and audio output routing.
 */
export function computeDeviceSignal(isPlayingAudio: boolean = false): DeviceSignal {
  const appState: AppStateStatus = AppState.currentState;
  const isWeb = Platform.OS === 'web' && typeof document !== 'undefined';
  const isDocumentHidden = isWeb ? document.hidden || document.visibilityState === 'hidden' : false;

  // 1. Bluetooth / external audio routing takes priority during active consumption
  if (isBluetoothConnected) {
    return 'bluetooth_connected';
  }

  // 2. Screen is visibly active and in foreground
  if (appState === 'active' && !isDocumentHidden) {
    return 'screen_on';
  }

  // 3. User locked the screen while audio continues playing in background
  if (isPlayingAudio && (isDocumentHidden || appState === 'inactive' || appState === 'background')) {
    return 'screen_off';
  }

  // 4. App is explicitly backgrounded (e.g. app switcher, minimized)
  if (appState === 'background') {
    return 'app_backgrounded';
  }

  // 5. Inactive (e.g. notification shade or app transition) without active audio playback
  if (appState === 'inactive' || isDocumentHidden) {
    return 'app_backgrounded';
  }

  return 'screen_on';
}

function notifySignalChange(isPlaying: boolean = false) {
  const nextSignal = computeDeviceSignal(isPlaying);
  if (nextSignal !== currentSignal) {
    currentSignal = nextSignal;
    listeners.forEach((listener) => listener(nextSignal));
  }
}

// AppState listener
AppState.addEventListener('change', () => {
  notifySignalChange();
});

// Web visibility change listener
if (Platform.OS === 'web' && typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    notifySignalChange();
  });
}

/**
 * Returns the current device signal state.
 */
export function getDeviceSignal(isPlayingAudio: boolean = false): DeviceSignal {
  currentSignal = computeDeviceSignal(isPlayingAudio);
  return currentSignal;
}

/**
 * Manually report bluetooth connectivity status (e.g. from Native modules or player events).
 */
export function setBluetoothConnected(connected: boolean) {
  isBluetoothConnected = connected;
  notifySignalChange();
}

/**
 * Subscribe to device signal transitions.
 */
export function subscribeDeviceSignal(listener: (signal: DeviceSignal) => void): () => void {
  listeners.add(listener);
  listener(currentSignal);
  return () => {
    listeners.delete(listener);
  };
}
