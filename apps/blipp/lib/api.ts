import type { AuthTokens, PlaybackTelemetryPayload, User } from './types';

// All API calls are relative — the SPA and API share the same origin
// via Traefik routing: / → blipp-app, /api or /v1 → auth-service
const BASE = '/api';

// ─── Request Helper ───────────────────────────────────────────────────────────

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  token?: string | null;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, token, ...rest } = opts;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE}${path}`, {
    ...rest,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
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
  async login(req: LoginRequest): Promise<{ tokens: AuthTokens; user: User }> {
    const r = await request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: req,
    });
    const tokens = toTokens(r);
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
    const r = await request<LoginResponse>('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });
    return toTokens(r);
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
