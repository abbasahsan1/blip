import AsyncStorage from '@react-native-async-storage/async-storage';
import type { AuthTokens, PlaybackTelemetryPayload, User } from './types';

// All API calls are relative — the SPA and API share the same origin
// via Traefik routing: / → blipp-app, /v1 or /api → backend services
const BASE = '/v1';

// ─── Request Helper ───────────────────────────────────────────────────────────

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  token?: string | null;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, token, ...rest } = opts;

  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string>),
  };

  // Only set application/json if body is not FormData
  if (!(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  // Automatically attach stored Keycloak access token if not explicitly provided
  let activeToken = token;
  if (activeToken === undefined) {
    try {
      activeToken = await AsyncStorage.getItem('blipp:access_token');
    } catch {
      activeToken = null;
    }
  }

  if (activeToken) {
    headers['Authorization'] = `Bearer ${activeToken}`;
  }

  const endpointUrl = path.startsWith('/v1') || path.startsWith('/api') ? path : `${BASE}${path}`;

  const response = await fetch(endpointUrl, {
    ...rest,
    headers,
    body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorEnvelope = (data as { error?: { message?: string; code?: string; request_id?: string } })?.error;
    const message =
      errorEnvelope?.message ??
      (data as { detail?: string })?.detail ??
      (data as { message?: string })?.message ??
      `Request failed: ${response.status}`;
    
    throw new ApiError(message, response.status, data, errorEnvelope?.code, errorEnvelope?.request_id);
  }

  return data as T;
}

// ─── Error Type ───────────────────────────────────────────────────────────────

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
    id: r.id || r.sub || '',
    email: r.email,
    username: r.username || r.preferred_username || '',
    displayName: displayName || r.username || r.preferred_username || '',
    avatarUrl: r.picture,
  };
}

export const authApi = {
  async requestOtp(email: string): Promise<{ message: string; success: boolean }> {
    return request<{ message: string; success: boolean }>('/auth/otp/request', {
      method: 'POST',
      body: { email },
    });
  },

  async verifyOtp(email: string, code: string): Promise<{ tokens: AuthTokens; user: User }> {
    const r = await request<LoginResponse>('/auth/otp/verify', {
      method: 'POST',
      body: { email, code },
    });
    const tokens = toTokens(r);
    const me = await authApi.me(tokens.accessToken);
    return { tokens, user: me };
  },

  async getOAuthUrl(provider: 'google' | 'apple'): Promise<string> {
    const res = await request<{ provider: string; authorization_url: string }>(`/auth/oauth/${provider}/url`);
    return res.authorization_url;
  },

  async signInWithOAuth(provider: 'google' | 'apple', idToken?: string, code?: string): Promise<{ tokens: AuthTokens; user: User }> {
    const r = await request<LoginResponse>(`/auth/oauth/${provider}`, {
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
    await request('/auth/register', { method: 'POST', body: req });
    // Auto sign-in after registration
    return authApi.login({ email: req.email, password: req.password });
  },

  async me(token: string): Promise<User> {
    const r = await request<MeResponse>('/auth/me', { token });
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
    await request('/auth/logout', { method: 'POST', token }).catch(() => {
      // Ignore logout errors — we'll clear local state regardless
    });
  },
};

// ─── Telemetry API ────────────────────────────────────────────────────────────

export const telemetryApi = {
  /**
   * Emits playback progress telemetry along with active device signal state
   * (screen_on, app_backgrounded, screen_off, bluetooth_connected).
   */
  async recordPlayProgress(payload: PlaybackTelemetryPayload): Promise<void> {
    try {
      await request('/telemetry/playback', {
        method: 'POST',
        body: payload,
      });
    } catch {
      // Non-blocking telemetry — fail silently to never disrupt audio consumption
    }
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
  audio_url: string;
  audio_variants: { standard?: string; low?: string; high?: string };
  duration_seconds: number;
}

export interface FeedResponse {
  items: FeedResponseItem[];
  next_cursor: string | null;
}

export const blippApi = {
  async getFeed(): Promise<FeedResponse> {
    return request<FeedResponse>('/blipps/feed', { method: 'GET' });
  },

  async uploadBlipp(formData: FormData, token?: string): Promise<BlippUploadResponse> {
    return request<BlippUploadResponse>('/blipps/upload', {
      method: 'POST',
      body: formData,
      token,
    });
  },
};
