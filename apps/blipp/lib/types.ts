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

export interface SponsorInfo {
  name?: string;
  brand_name?: string;
  tagline?: string;
  cta_text: string;
  cta_url: string;
  logo_url?: string;
}

export interface AdMetadata {
  campaign_id: string;
  impression_url?: string;
  click_url?: string;
}

export type UploadStatus = 'idle' | 'uploading' | 'transcoding' | 'completed' | 'failed';

export interface Blipp {
  id: string;
  blipp_id?: string;
  title: string;
  description?: string | null;
  author: string;
  authorId: string;
  creator_id?: string;
  duration: number; // seconds
  duration_seconds?: number;
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
  sourceType?: 'podcast' | 'interview' | 'documentary' | 'other' | string;
  // Server-hydrated sponsored ad slot (§6.4)
  is_sponsored?: boolean;
  is_ad?: boolean;
  sponsor?: SponsorInfo;
  ad_metadata?: AdMetadata;
  // User engagement state (§5.3, §6.7)
  is_saved?: boolean;
  is_following?: boolean;
  creator?: {
    id?: string;
    username?: string;
    display_name?: string;
    avatar_url?: string | null;
  };
}

// Alias AudioPost to Blipp for seamless compatibility
export type AudioPost = Blipp;
export type BlippItem = Blipp;

export interface StoryItem {
  story_id: string;
  creator_id: string;
  audio_url: string;
  duration_seconds: number;
  expires_at: string;
  created_at: string;
  creator?: {
    username?: string;
    display_name?: string;
    avatar_url?: string | null;
  };
}

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
  tokens?: { accessToken: string; refreshToken?: string } | null;
}
