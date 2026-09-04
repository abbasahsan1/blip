import type { AuthTokens, User } from './types';

// All API calls are relative — the SPA and API share the same origin
// via Traefik routing: / → blipp-app, /api → auth-service
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
    const message =
      (data as { detail?: string })?.detail ??
      (data as { message?: string })?.message ??
      `Request failed: ${response.status}`;
    throw new ApiError(message, response.status, data);
  }

  return data as T;
}

// ─── Error Type ───────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly data: unknown = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ─── Auth API ─────────────────────────────────────────────────────────────────

interface LoginRequest {
  email: string;
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
  sub: string;
  email: string;
  preferred_username: string;
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
  return {
    id: r.sub,
    email: r.email,
    username: r.preferred_username,
    displayName: r.name,
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
