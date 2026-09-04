// ─── Auth ────────────────────────────────────────────────────────────────────

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface User {
  id: string;
  email: string;
  username: string;
  displayName?: string;
  avatarUrl?: string;
  createdAt?: string;
}

export interface AuthFailure {
  field?: 'email' | 'password' | 'username' | 'credentials' | 'general';
  message: string;
  code?: string;
}

// ─── Audio & Feed ─────────────────────────────────────────────────────────────

export type FeedSort = 'most_listened' | 'newest';

export interface AudioVariants {
  low: string;
  standard: string;
  high: string;
}

export interface Blipp {
  id: string;
  title: string;
  author: string;
  authorId: string;
  duration: number; // seconds
  audio_url: string; // canonical URL
  audio_variants?: AudioVariants; // quality tier variants
  audioUrl?: string; // backwards compatibility alias
  coverGradient?: [string, string]; // gradient start/end
  listenCount: number;
  likeCount: number;
  isLiked?: boolean;
  tags?: string[];
  createdAt: string;
  // Source metadata
  sourceName?: string; // e.g. "The Tim Ferriss Show", "Lex Fridman Podcast"
  sourceType?: 'podcast' | 'interview' | 'documentary' | 'other';
}

// Alias AudioPost to Blipp for seamless compatibility
export type AudioPost = Blipp;

export interface FeedState {
  posts: Blipp[];
  sort: FeedSort;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
}

// ─── Telemetry & Device Signals ───────────────────────────────────────────────

export type DeviceSignal =
  | 'screen_on'
  | 'screen_off'
  | 'bluetooth_connected'
  | 'app_backgrounded';

export interface PlaybackTelemetryPayload {
  blipp_id: string;
  position_seconds: number;
  duration_seconds: number;
  device_signal: DeviceSignal;
}

// ─── Player ──────────────────────────────────────────────────────────────────

export interface PlayerState {
  currentId: string | null;
  isPlaying: boolean;
  isBuffering: boolean;
  position: number; // ms
  duration: number; // ms
  speed: 1 | 1.5 | 2;
  error: string | null;
}

// ─── Session ─────────────────────────────────────────────────────────────────

export type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated';

export interface SessionState {
  status: SessionStatus;
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
}
