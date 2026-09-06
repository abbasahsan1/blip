import { router } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSessionStore } from './store/sessionStore';
import type { AuthTokens, PlaybackTelemetryPayload, User } from './types';

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

// ─── Base URL Configuration ───────────────────────────────────────────────────

export const getApiBaseUrl = (): string => {
  if (process.env.EXPO_PUBLIC_API_URL) {
    return process.env.EXPO_PUBLIC_API_URL.replace(/\/+$/, '');
  }
  // In production browser environments where /v1 and /api are reverse-proxied via ingress
  if (typeof window !== 'undefined' && window.location && window.location.origin) {
    if (!window.location.hostname.includes('localhost') && !window.location.hostname.includes('127.0.0.1')) {
      return '';
    }
  }
  return 'http://localhost:8000';
};

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

  const baseUrl = getApiBaseUrl();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const endpointUrl = baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;

  const response = await fetch(endpointUrl, {
    ...rest,
    headers,
    body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  // Intercept 401 Unauthorized: clear session state and redirect to /auth/sign-in
  if (response.status === 401) {
    useSessionStore.getState().clearSession();
    try {
      router.replace('/auth/sign-in');
    } catch {
      // Router not mounted yet
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

export const api = {
  get: <T = any>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'GET' }),

  post: <T = any>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'POST', body }),

  put: <T = any>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'PUT', body }),

  delete: <T = any>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> =>
    requestRaw<T>(path, { ...options, method: 'DELETE' }),
};

// ─── Auth API ─────────────────────────────────────────────────────────────────

interface LoginRequest {
  email?: string;
  username?: string;
  password: string;
}

interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

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
  async requestOtp(email: string): Promise<{ message: string; success: boolean }> {
    return request<{ message: string; success: boolean }>('/v1/auth/otp/request', {
      method: 'POST',
      body: { email },
    });
  },

  async verifyOtp(email: string, code: string): Promise<{ tokens: AuthTokens; user: User }> {
    const r = await request<LoginResponse>('/v1/auth/otp/verify', {
      method: 'POST',
      body: { email, code },
    });
    const tokens = toTokens(r);
    const me = await authApi.me(tokens.accessToken);
    return { tokens, user: me };
  },

  async getOAuthUrl(provider: 'google' | 'apple'): Promise<string> {
    const res = await request<{ provider: string; authorization_url: string }>(`/v1/auth/oauth/${provider}/url`);
    return res.authorization_url;
  },

  async signInWithOAuth(provider: 'google' | 'apple', idToken?: string, code?: string): Promise<{ tokens: AuthTokens; user: User }> {
    const r = await request<LoginResponse>(`/v1/auth/oauth/${provider}`, {
      method: 'POST',
      body: { provider, id_token: idToken, code },
    });
    const tokens = toTokens(r);
    const me = await authApi.me(tokens.accessToken);
    return { tokens, user: me };
  },

  async login(req: LoginRequest): Promise<{ tokens: AuthTokens; user: User }> {
    const username = req.username || req.email || '';
    const password = req.password;
    const body = `client_id=blipp-app&grant_type=password&username=${encodeURIComponent(username)}&password=${password}`;

    const res = await fetch('/keycloak/realms/blipp/protocol/openid-connect/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body,
    });

    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = data?.error_description || data?.error || `Login failed: ${res.status}`;
      throw new ApiError(msg, res.status, data);
    }

    const tokens = toTokens(data as LoginResponse);
    const me = await authApi.me(tokens.accessToken);
    return { tokens, user: me };
  },

  async register(req: RegisterRequest): Promise<{ tokens: AuthTokens; user: User }> {
    await request('/v1/auth/register', { method: 'POST', body: req });
    return authApi.login({ email: req.email, password: req.password });
  },

  async me(token: string): Promise<User> {
    const r = await request<MeResponse>('/v1/auth/me', { token });
    return toUser(r);
  },

  async refresh(refreshToken: string): Promise<AuthTokens> {
    const params = new URLSearchParams();
    params.append('client_id', 'blipp-app');
    params.append('grant_type', 'refresh_token');
    params.append('refresh_token', refreshToken);

    const res = await fetch('/keycloak/realms/blipp/protocol/openid-connect/token', {
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
}

export interface FeedResponse {
  items: FeedResponseItem[];
  next_cursor: string | null;
}

export interface UserProfile {
  user_id: string;
  username: string;
  display_name: string;
  bio?: string | null;
  avatar_url?: string | null;
  created_at?: string | null;
}

export const profileApi = {
  async getMyProfile(): Promise<UserProfile> {
    const res = await api.get<UserProfile>('/v1/profiles/me');
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

export const blippApi = {
  async getBlipps(): Promise<FeedResponse> {
    const res = await api.get<FeedResponse>('/v1/blipps');
    return res.data;
  },

  async getFeed(): Promise<FeedResponse> {
    const res = await api.get<FeedResponse>('/v1/blipps');
    return res.data;
  },

  async uploadBlipp(formData: FormData, token?: string): Promise<BlippUploadResponse> {
    const res = await requestRaw<BlippUploadResponse>('/v1/blipps/upload', {
      method: 'POST',
      body: formData,
      token,
    });
    return res.data;
  },
};
