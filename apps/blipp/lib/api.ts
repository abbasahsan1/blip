import { router } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSessionStore } from './store/sessionStore';
import type {
  AuthTokens,
  PlaybackTelemetryPayload,
  User,
  BlippItem,
  StoryItem,
  DMMessageItem,
  DMThreadItem,
  MessageListResponse,
} from './types';

// ─── Platform Error Envelope ───────────────────────────────────────────────────

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly data: unknown = null,
    public readonly code?: string,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ─── Base URL & Traefik Gateway Configuration ────────────────────────────────

export const getGatewayUrl = (): string => {
  if (process.env.EXPO_PUBLIC_GATEWAY_URL) {
    return process.env.EXPO_PUBLIC_GATEWAY_URL.replace(/\/+$/, '');
  }
  if (process.env.EXPO_PUBLIC_API_URL) {
    const raw = process.env.EXPO_PUBLIC_API_URL.replace(/\/+$/, '');
    if (raw.includes(':8000')) {
      return raw.replace(':8000', ':8419').replace(/\/v1$/, '');
    }
    return raw.replace(/\/v1$/, '');
  }
  if (typeof window !== 'undefined' && window.location && window.location.origin) {
    if (!window.location.hostname.includes('localhost') && !window.location.hostname.includes('127.0.0.1')) {
      return window.location.origin;
    }
  }
  return 'http://localhost:8419';
};

export const getApiBaseUrl = (): string => getGatewayUrl();
export const getContentIngestUrl = (): string => getGatewayUrl();
export const getFeedServiceUrl = (): string => getGatewayUrl();
export const getSocialGraphUrl = (): string => getGatewayUrl();
export const getMessagingUrl = (): string => getGatewayUrl();
export const getModerationUrl = (): string => getGatewayUrl();
export const getMinioPublicUrl = (): string => getGatewayUrl();

export const getKeycloakUrl = (): string => {
  if (process.env.EXPO_PUBLIC_KEYCLOAK_URL) {
    const raw = process.env.EXPO_PUBLIC_KEYCLOAK_URL.replace(/\/+$/, '');
    if (!raw.includes(':8080')) return raw;
  }
  return getGatewayUrl();
};

export function resolveMediaUrl(url: string | null | undefined): string {
  if (!url) return '';
  const gateway = process.env.EXPO_PUBLIC_GATEWAY_URL || getGatewayUrl();
  // Replace relative paths, localhost:9000, 127.0.0.1:9000, or minio:9000 with the single gateway URL
  if (url.startsWith('/')) {
    return `${gateway.replace(/\/+$/, '')}${url}`;
  }
  return url
    .replace(/^https?:\/\/(localhost|127\.0\.0\.1|minio|minio\.blipp\.svc\.cluster\.local):9000/, gateway.replace(/\/+$/, ''))
    .replace(/^https?:\/\/[^/]+:9000/, gateway.replace(/\/+$/, ''));
}

export const resolvePublicAudioUrl = resolveMediaUrl;

export interface ApiResponse<T = any> {
  data: T;
  status: number;
  headers: Headers;
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  token?: string | null;
}

// ─── Centralized Request Execution & Interception ──────────────────────────────

export async function requestRaw<T = any>(
  path: string,
  opts: RequestOptions = {},
): Promise<ApiResponse<T>> {
  const { body, token, ...rest } = opts;

  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string>),
  };

  // Only set application/json if body is not FormData
  if (!(body instanceof FormData) && body !== undefined && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  // Intercept outgoing requests: inject Bearer token from useSessionStore
  let activeToken = token;
  if (activeToken === undefined) {
    activeToken = useSessionStore.getState().tokens?.accessToken || useSessionStore.getState().accessToken;
    if (!activeToken) {
      try {
        activeToken = await AsyncStorage.getItem('blipp:access_token');
      } catch {
        activeToken = null;
      }
    }
  }

  if (activeToken && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${activeToken}`;
  }

  const gateway = getGatewayUrl();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const endpointUrl = `${gateway}${normalizedPath}`;

  const response = await fetch(endpointUrl, {
    ...rest,
    headers,
    body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  // Intercept 401 Unauthorized: attempt auto-refresh
  if (response.status === 401) {
    const refreshToken = useSessionStore.getState().tokens?.refreshToken;
    let refreshSuccess = false;
    
    if (refreshToken) {
      try {
        const newTokens = await authApi.refresh(refreshToken);
        const me = await authApi.me(newTokens.accessToken);
        useSessionStore.getState().setSessionTokens(newTokens, me);
        
        headers['Authorization'] = `Bearer ${newTokens.accessToken}`;
        const retryResponse = await fetch(endpointUrl, {
          ...rest,
          headers,
          body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
        });
        
        const retryData = await retryResponse.json().catch(() => null);
        if (!retryResponse.ok) {
            const errEnv = (retryData as ApiErrorResponse)?.error;
            throw new ApiError('Retry failed', retryResponse.status, retryData, errEnv?.code, errEnv?.request_id);
        }
        return { data: retryData as T, status: retryResponse.status, headers: retryResponse.headers };
      } catch (e) {
        refreshSuccess = false;
      }
    }
    
    if (!refreshSuccess) {
        useSessionStore.getState().clearSession();
        try {
          router.replace('/auth/sign-in');
        } catch {}
    }
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorEnvelope = (data as ApiErrorResponse)?.error;
    const message =
      errorEnvelope?.message ??
      (data as { detail?: string })?.detail ??
      (data as { message?: string })?.message ??
      `Request failed with status ${response.status}`;

    throw new ApiError(
      message,
      response.status,
      data,
      errorEnvelope?.code,
      errorEnvelope?.request_id,
    );
  }

  return {
    data: data as T,
    status: response.status,
    headers: response.headers,
  };
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await requestRaw<T>(path, opts);
  return res.data;
}

// ─── Centralized API Client (Axios-like verbs returning { data, status, headers }) ──

// ─── Typed Social, Saves, and Stories API Methods (§5.3, §5.4, §6.7) ───────────

export async function followUser(userId: string): Promise<void> {
  await requestRaw<void>(`/v1/social/follow/${userId}`, { method: 'POST' });
}

export async function unfollowUser(userId: string): Promise<void> {
  await requestRaw<void>(`/v1/social/follow/${userId}`, { method: 'DELETE' });
}

export interface LikeActionResponse {
  success: boolean;
  blipp_id: string;
  is_liked: boolean;
}

export async function likeBlipp(blippId: string): Promise<LikeActionResponse> {
  const res = await requestRaw<LikeActionResponse>(`/v1/likes/${blippId}`, { method: 'POST' });
  return res.data;
}

export async function saveBlipp(blippId: string): Promise<void> {
  await requestRaw<void>(`/v1/blipps/${blippId}/save`, { method: 'POST' });
}

export async function unsaveBlipp(blippId: string): Promise<void> {
  await requestRaw<void>(`/v1/blipps/${blippId}/save`, { method: 'DELETE' });
}

export async function getSavedBlipps(): Promise<BlippItem[]> {
  const res = await requestRaw<{ items: any[] } | any[]>('/v1/blipps/saved', { method: 'GET' });
  const rawItems = Array.isArray(res.data) ? res.data : (res.data as any)?.items || [];
  const GRADIENTS: [string, string][] = [
    ['#2563eb', '#8b5cf6'],
    ['#6366f1', '#a855f7'],
    ['#0f172a', '#1e3a5f'],
    ['#064e3b', '#065f46'],
  ];
  return rawItems.map((item: any, idx: number) => {
    const rawStandard = item.audio_variants?.standard || item.audio_url || '';
    const standardUrl = resolvePublicAudioUrl(rawStandard);
    return {
      id: item.blipp_id || item.id,
      blipp_id: item.blipp_id || item.id,
      title: item.title || 'Saved Broadcast',
      description: item.description,
      author: item.display_name || item.author || (item.username ? `@${item.username}` : `Creator ${item.creator_id ? item.creator_id.slice(0, 6) : ''}`),
      authorId: item.creator_id || '',
      creator_id: item.creator_id,
      duration: item.duration_seconds || item.duration || 30,
      duration_seconds: item.duration_seconds || item.duration || 30,
      audio_url: standardUrl,
      audioUrl: standardUrl,
      audio_variants: {
        standard: standardUrl,
        low: resolvePublicAudioUrl(item.audio_variants?.low || rawStandard),
        high: resolvePublicAudioUrl(item.audio_variants?.high || rawStandard),
      },
      coverGradient: GRADIENTS[idx % GRADIENTS.length],
      listenCount: item.listens_count || item.listenCount || 0,
      likeCount: item.likes_count || item.likeCount || 0,
      isLiked: false,
      is_saved: true,
      createdAt: item.saved_at || item.created_at || new Date().toISOString(),
    };
  });
}

export async function getStories(): Promise<StoryItem[]> {
  const res = await requestRaw<StoryItem[] | { items: StoryItem[] }>('/v1/stories', { method: 'GET' });
  const rawList: StoryItem[] = Array.isArray(res.data) ? res.data : (res.data as any)?.items || [];
  return rawList.map((story) => ({
    ...story,
    media_url: resolveMediaUrl((story as any).media_url || (story as any).audio_url),
    audio_url: resolveMediaUrl((story as any).audio_url || (story as any).media_url),
  }));
}

export async function uploadStory(formData: FormData): Promise<void> {
  await requestRaw<void>('/v1/stories', { method: 'POST', body: formData });
}

// ─── Direct Messaging Methods (§5.4) ──────────────────────────────────────────

export async function getThreads(limit = 20, offset = 0): Promise<DMThreadItem[]> {
  const res = await requestRaw<DMThreadItem[]>(`/v1/messages/threads?limit=${limit}&offset=${offset}`, { method: 'GET' });
  return Array.isArray(res.data) ? res.data : [];
}

export async function getDMThreads(limit = 20, offset = 0): Promise<DMThreadItem[]> {
  return getThreads(limit, offset);
}

export async function createThread(recipientId: string): Promise<DMThreadItem> {
  const res = await requestRaw<DMThreadItem>('/v1/messages/threads', {
    method: 'POST',
    body: { recipient_id: recipientId },
  });
  return res.data;
}

export async function getThreadMessages(
  threadId: string,
  limit = 30,
  cursor?: string | null,
): Promise<MessageListResponse> {
  let path = `/v1/messages/threads/${threadId}?limit=${limit}`;
  if (cursor) path += `&cursor=${encodeURIComponent(cursor)}`;
  const res = await requestRaw<MessageListResponse>(path, { method: 'GET' });
  return res.data;
}

export async function sendMessage(
  threadId: string,
  payload: {
    message_type: 'text' | 'blipp_share';
    body?: string;
    blipp_id?: string;
  },
): Promise<DMMessageItem> {
  const res = await requestRaw<DMMessageItem>(`/v1/messages/threads/${threadId}`, {
    method: 'POST',
    body: payload,
  });
  return res.data;
}

export async function getProfileByUsername(username: string): Promise<UserProfile> {
  const res = await requestRaw<UserProfile>(`/v1/profiles/${encodeURIComponent(username)}`, { method: 'GET' });
  return res.data;
}

export async function searchProfiles(query: string): Promise<Array<{
  user_id: string;
  username: string;
  display_name?: string | null;
  avatar_url?: string | null;
}>> {
  const clean = query.trim().replace(/^@/, '');
  if (!clean) return [];
  try {
    const profile = await getProfileByUsername(clean);
    if (profile && profile.user_id) {
      return [
        {
          user_id: profile.user_id,
          username: profile.username,
          display_name: profile.display_name,
          avatar_url: profile.avatar_url,
        },
      ];
    }
  } catch {
    // Return empty on not found
  }
  return [];
}

export async function getUserFollowing(userId: string): Promise<{ items: Array<{ user_id: string; username: string; display_name?: string; avatar_url?: string | null }> }> {
  const res = await requestRaw<{ items: Array<{ user_id: string; username: string; display_name?: string; avatar_url?: string | null }> }>(
    `/v1/social/${userId}/following`,
    { method: 'GET' },
  );
  return res.data || { items: [] };
}

export async function getFeed(cursor?: string | null): Promise<FeedResponse> {
  const path = cursor ? `/v1/feed?cursor=${encodeURIComponent(cursor)}` : '/v1/feed';
  const res = await requestRaw<FeedResponse>(path, { method: 'GET' });
  const rawItems = res.data?.items || [];
  const normalizedItems = rawItems.map((item) => {
    const rawStandard = item.audio_variants?.standard || item.audio_url || '';
    const standardUrl = resolveMediaUrl(rawStandard);
    return {
      ...item,
      audio_url: standardUrl,
      audio_variants: {
        standard: standardUrl,
        low: resolveMediaUrl(item.audio_variants?.low || rawStandard),
        high: resolveMediaUrl(item.audio_variants?.high || rawStandard),
      },
    };
  });
  return {
    items: normalizedItems,
    next_cursor: res.data?.next_cursor ?? null,
  };
}

export const api = {
  get: <T = any>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'GET' }),

  post: <T = any>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'POST', body }),

  put: <T = any>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'PUT', body }),

  delete: <T = any>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'DELETE' }),

  login: apiLogin,
  followUser,
  unfollowUser,
  likeBlipp,
  saveBlipp,
  unsaveBlipp,
  getFeed,
  getSavedBlipps,
  getStories,
  uploadStory,
  getThreads,
  getDMThreads,
  searchProfiles,
  createThread,
  getThreadMessages,
  sendMessage,
  getProfileByUsername,
  getUserFollowing,
  resolveMediaUrl,
};

// ─── Auth API ─────────────────────────────────────────────────────────────────

export interface LoginRequest {
  email?: string;
  username?: string;
  password: string;
}

export interface RegisterRequest {
  username?: string;
  email: string;
  password: string;
  displayName?: string;
}

export async function apiLogin(
  emailOrReq: string | LoginRequest,
  maybePassword?: string,
): Promise<{ tokens: AuthTokens; user: User; access_token: string; refresh_token: string }> {
  const email = typeof emailOrReq === 'string' ? emailOrReq : emailOrReq.email;
  const username = typeof emailOrReq === 'string' ? undefined : emailOrReq.username;
  const password = typeof emailOrReq === 'string' ? maybePassword || '' : emailOrReq.password;

  const loginId = username || email || '';

  const params = new URLSearchParams();
  params.append('client_id', 'blipp-app');
  params.append('grant_type', 'password');
  params.append('username', loginId);
  params.append('password', password || '');

  const res = await fetch(`${getKeycloakUrl()}/realms/blipp/protocol/openid-connect/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(data?.error_description || 'Login failed', res.status, data);
  }

  const tokens = toTokens(data as LoginResponse);
  const me = await authApi.me(tokens.accessToken);
  
  return { 
    tokens, 
    user: me, 
    access_token: tokens.accessToken, 
    refresh_token: tokens.refreshToken 
  };
}

// Removed apiRegister to prevent Admin API usage on the client

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

interface MeResponse {
  id?: string;
  user_id?: string;
  sub?: string;
  email: string;
  username?: string;
  preferred_username?: string;
  first_name?: string;
  last_name?: string;
  name?: string;
  picture?: string;
}

function toTokens(r: LoginResponse): AuthTokens {
  return {
    accessToken: r.access_token,
    refreshToken: r.refresh_token,
    expiresIn: r.expires_in,
  };
}

function toUser(r: MeResponse): User {
  const displayName = r.name || (r.first_name ? `${r.first_name} ${r.last_name || ''}`.trim() : undefined);
  return {
    id: r.id || r.user_id || r.sub || '',
    email: r.email,
    username: r.username || r.preferred_username || '',
    displayName: displayName || r.username || r.preferred_username || '',
    avatarUrl: r.picture,
  };
}

export const authApi = {
  login: apiLogin,

  async me(token: string): Promise<User> {
    const res = await fetch(`${getKeycloakUrl()}/realms/blipp/protocol/openid-connect/userinfo`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new ApiError('Failed to fetch user info', res.status, data);
    }
    return toUser(data as MeResponse);
  },

  async refresh(refreshToken: string): Promise<AuthTokens> {
    const params = new URLSearchParams();
    params.append('client_id', 'blipp-app');
    params.append('grant_type', 'refresh_token');
    params.append('refresh_token', refreshToken);

    const res = await fetch(`${getKeycloakUrl()}/realms/blipp/protocol/openid-connect/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });

    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new ApiError(data?.error_description || 'Refresh failed', res.status, data);
    }
    return toTokens(data as LoginResponse);
  },

  async logout(token: string): Promise<void> {
    await request('/v1/auth/logout', { method: 'POST', token }).catch(() => {
      // Ignore logout errors - local state will be wiped
    });
  },
};

// ─── Telemetry API ────────────────────────────────────────────────────────────

export const telemetryApi = {
  async recordPlayProgress(payload: PlaybackTelemetryPayload): Promise<void> {
    try {
      await api.post('/v1/events', payload);
    } catch {
      // Non-blocking telemetry
    }
  },
};

export interface UploadResponse {
  upload_id: string;
  status: string;
  message: string;
}

export interface UploadStatusResponse {
  upload_id: string;
  creator_id: string;
  raw_file_url: string;
  upload_type: string;
  processing_status: 'queued' | 'transcoding' | 'done' | 'failed';
  title?: string | null;
  description?: string | null;
  created_at?: string | null;
}

export const uploadApi = {
  async upload(formData: FormData, token?: string): Promise<UploadResponse> {
    const res = await requestRaw<UploadResponse>('/v1/uploads', {
      method: 'POST',
      body: formData,
      token,
    });
    return res.data;
  },

  async getStatus(uploadId: string, token?: string): Promise<UploadStatusResponse> {
    const res = await requestRaw<UploadStatusResponse>(`/v1/uploads/${uploadId}`, {
      method: 'GET',
      token,
    });
    return res.data;
  },
};

// ─── Blipps Content API ───────────────────────────────────────────────────────

export interface BlippUploadResponse {
  blipp_id: string;
  creator_id: string;
  title: string;
  audio_url: string;
  audio_variants: { standard?: string; low?: string; high?: string };
  duration_seconds: number;
  status: string;
  created_at?: string;
}

export interface FeedResponseItem {
  blipp_id: string;
  creator_id: string;
  title: string;
  description?: string | null;
  audio_url: string;
  audio_variants: { standard?: string; low?: string; high?: string };
  duration_seconds: number;
  author?: string;
  username?: string;
  display_name?: string;
  avatar_url?: string;
  listens_count?: number;
  listenCount?: number;
  likes_count?: number;
  likeCount?: number;
  isLiked?: boolean;
  is_liked?: boolean;
  is_ad?: boolean;
  is_sponsored?: boolean;
  is_saved?: boolean;
  is_following?: boolean;
  creator?: {
    id: string;
    handle: string;
    display_name: string;
    avatar_url?: string;
  };
  sponsor?: {
    brand_name: string;
    cta_text: string;
    cta_url: string;
    tagline: string;
  };
  tags?: string[];
  sourceName?: string;
  created_at?: string;
}

export interface FeedResponse {
  items: FeedResponseItem[];
  next_cursor: string | null;
}

export interface UserProfile {
  user_id: string;
  username: string;
  display_name?: string | null;
  bio?: string | null;
  avatar_url?: string | null;
  is_creator?: boolean;
  verification_status?: string;
  created_at?: string | null;
  followers_count?: number;
  following_count?: number;
  is_following?: boolean;
}

export interface FollowActionResponse {
  success: boolean;
  follower_id: string;
  followee_id: string;
  is_following: boolean;
}

export interface FollowListResponse {
  items: UserProfile[];
  total: number;
  limit: number;
  offset: number;
}

export const profileApi = {
  async claimUsername(data: {
    username: string;
    display_name?: string;
    bio?: string;
    avatar_url?: string;
  }): Promise<UserProfile> {
    const res = await requestRaw<UserProfile>('/v1/profiles', {
      method: 'POST',
      body: data,
    });
    return res.data;
  },

  async getMyProfile(): Promise<UserProfile> {
    const res = await api.get<UserProfile>('/v1/profiles/me');
    return res.data;
  },

  async getProfile(username: string): Promise<UserProfile> {
    const res = await api.get<UserProfile>(`/v1/profiles/${encodeURIComponent(username)}`);
    return res.data;
  },

  async updateMyProfile(update: {
    display_name?: string;
    bio?: string;
    avatar_url?: string;
  }): Promise<UserProfile> {
    const res = await requestRaw<UserProfile>('/v1/profiles/me', {
      method: 'PATCH',
      body: update,
    });
    return res.data;
  },
};

export const socialApi = {
  async like(blippId: string): Promise<LikeActionResponse> {
    return likeBlipp(blippId);
  },

  async follow(userId: string): Promise<FollowActionResponse> {
    const res = await requestRaw<FollowActionResponse>(`/v1/social/follow/${userId}`, {
      method: 'POST',
    });
    return res.data;
  },

  async unfollow(userId: string): Promise<FollowActionResponse> {
    const res = await requestRaw<FollowActionResponse>(`/v1/social/follow/${userId}`, {
      method: 'DELETE',
    });
    return res.data;
  },

  async getFollowers(
    userId: string,
    limit = 20,
    offset = 0,
  ): Promise<FollowListResponse> {
    const res = await api.get<FollowListResponse>(
      `/v1/social/${userId}/followers?limit=${limit}&offset=${offset}`,
    );
    return res.data;
  },

  async getFollowing(
    userId: string,
    limit = 20,
    offset = 0,
  ): Promise<FollowListResponse> {
    const res = await api.get<FollowListResponse>(
      `/v1/social/${userId}/following?limit=${limit}&offset=${offset}`,
    );
    return res.data;
  },
};

export const blippApi = {
  getBlipps: getFeed,
  getFeed: getFeed,

  async uploadBlipp(formData: FormData, token?: string): Promise<BlippUploadResponse> {
    const res = await requestRaw<BlippUploadResponse>('/v1/blipps/upload', {
      method: 'POST',
      body: formData,
      token,
    });
    return res.data;
  },
};
