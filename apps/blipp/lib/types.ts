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

// ─── Feed ────────────────────────────────────────────────────────────────────

export type FeedSort = 'most_listened' | 'newest';

export interface AudioPost {
  id: string;
  title: string;
  author: string;
  authorId: string;
  duration: number; // seconds
  audioUrl: string;
  coverGradient?: [string, string]; // gradient start/end
  listenCount: number;
  likeCount: number;
  isLiked?: boolean;
  tags?: string[];
  createdAt: string;
  // Source metadata
  sourceName?: string; // "The Tim Ferriss Show", "Lex Fridman Podcast"
  sourceType?: 'podcast' | 'interview' | 'documentary' | 'other';
}

export interface FeedState {
  posts: AudioPost[];
  sort: FeedSort;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
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
