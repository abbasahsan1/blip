import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { ApiError, authApi } from '../api';
import type { AuthFailure, SessionStatus, User } from '../types';

// ─── Storage Keys ─────────────────────────────────────────────────────────────

const KEY_ACCESS = 'blipp:access_token';
const KEY_REFRESH = 'blipp:refresh_token';

// ─── State ────────────────────────────────────────────────────────────────────

interface SessionStore {
  status: SessionStatus;
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  tokens: { accessToken: string; refreshToken?: string } | null;

  // UI feedback
  isSubmitting: boolean;
  error: AuthFailure | null;

  // Actions
  initialize: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (username: string, email: string, password?: string) => Promise<void>;
  signOut: () => Promise<void>;
  setSessionTokens: (tokens: { accessToken: string; refreshToken?: string }, user?: User | null) => Promise<void>;
  clearSession: () => void;
  clearError: () => void;
  refreshSession: () => Promise<boolean>;
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useSessionStore = create<SessionStore>((set, get) => ({
  status: 'loading',
  user: null,
  accessToken: null,
  refreshToken: null,
  tokens: null,
  isSubmitting: false,
  error: null,

  async initialize() {
    try {
      const [access, refresh] = await AsyncStorage.multiGet([KEY_ACCESS, KEY_REFRESH]);
      const accessToken = access[1];
      const refreshToken = refresh[1];

      if (!accessToken || !refreshToken) {
        set({ status: 'unauthenticated', tokens: null });
        return;
      }

      // Validate stored token
      try {
        const user = await authApi.me(accessToken);
        set({
          status: 'authenticated',
          user,
          accessToken,
          refreshToken,
          tokens: { accessToken, refreshToken },
        });
      } catch (err) {
        // Try refresh
        if (refreshToken) {
          const ok = await get().refreshSession();
          if (!ok) {
            await AsyncStorage.multiRemove([KEY_ACCESS, KEY_REFRESH]);
            set({ status: 'unauthenticated', accessToken: null, refreshToken: null, tokens: null });
          }
        } else {
          set({ status: 'unauthenticated', tokens: null });
        }
      }
    } catch {
      set({ status: 'unauthenticated', tokens: null });
    }
  },

  async signIn(email, password) {
    set({ isSubmitting: true, error: null });
    try {
      // 1. Post to Keycloak token endpoint
      const keycloakUrl = process.env.EXPO_PUBLIC_KEYCLOAK_URL?.replace(/\/+$/, '') || 'http://localhost:8419/keycloak';
      const tokenEndpoint = `${keycloakUrl}/realms/blipp/protocol/openid-connect/token`;
      
      const params = new URLSearchParams();
      params.append('client_id', 'blipp-app');
      params.append('grant_type', 'password');
      params.append('username', email);
      params.append('password', password);
      params.append('scope', 'openid profile email');

      const tokenRes = await fetch(tokenEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString(),
      });

      const tokenData = await tokenRes.json().catch(() => null);

      if (!tokenRes.ok) {
        throw new Error(tokenData?.error_description || 'Login failed');
      }

      const accessToken = tokenData.access_token;
      const refreshToken = tokenData.refresh_token;

      // 2. Fetch User Profile
      const userinfoEndpoint = `${keycloakUrl}/realms/blipp/protocol/openid-connect/userinfo`;
      const userRes = await fetch(userinfoEndpoint, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      
      const userData = await userRes.json().catch(() => null);
      if (!userRes.ok) {
        throw new Error('Failed to fetch user profile');
      }

      const displayName = userData.name || (userData.first_name ? `${userData.first_name} ${userData.last_name || ''}`.trim() : undefined);
      const user: User = {
        id: userData.sub || '',
        email: userData.email || email,
        username: userData.preferred_username || '',
        displayName: displayName || userData.preferred_username || '',
        avatarUrl: userData.picture,
      };

      await AsyncStorage.multiSet([
        [KEY_ACCESS, accessToken],
        [KEY_REFRESH, refreshToken],
      ]);

      set({
        status: 'authenticated',
        user,
        accessToken,
        refreshToken,
        tokens: { accessToken, refreshToken },
        isSubmitting: false,
      });
    } catch (err) {
      set({ isSubmitting: false, error: toFailure(err) });
    }
  },

  async signUpWithEmail(username, email, password) {
    set({ isSubmitting: true, error: null });
    try {
      // In-app registration via API is disabled for security reasons
      // Users should be redirected to the web portal or standard OIDC flow
      throw new Error('In-app registration is disabled. Please sign up via the web portal.');
    } catch (err) {
      set({ isSubmitting: false, error: toFailure(err) });
    }
  },

  async signOut() {
    const { accessToken } = get();
    if (accessToken) {
      await authApi.logout(accessToken);
    }
    await AsyncStorage.multiRemove([KEY_ACCESS, KEY_REFRESH]);
    set({ status: 'unauthenticated', user: null, accessToken: null, refreshToken: null, tokens: null });
  },

  async setSessionTokens(tokens, user) {
    await AsyncStorage.multiSet([
      [KEY_ACCESS, tokens.accessToken],
      ...(tokens.refreshToken ? [[KEY_REFRESH, tokens.refreshToken]] as const : []),
    ]);
    set({
      status: 'authenticated',
      user: user ?? { id: 'user_local', email: '', username: 'user', displayName: 'User' },
      accessToken: tokens.accessToken,
      refreshToken: tokens.refreshToken ?? null,
      tokens: { accessToken: tokens.accessToken, refreshToken: tokens.refreshToken },
      isSubmitting: false,
      error: null,
    });
  },

  clearSession() {
    void AsyncStorage.multiRemove([KEY_ACCESS, KEY_REFRESH]);
    set({
      status: 'unauthenticated',
      user: null,
      accessToken: null,
      refreshToken: null,
      tokens: null,
      error: null,
    });
  },

  clearError() {
    set({ error: null });
  },

  async refreshSession() {
    const { refreshToken } = get();
    if (!refreshToken) return false;
    try {
      const tokens = await authApi.refresh(refreshToken);
      const user = await authApi.me(tokens.accessToken);
      await AsyncStorage.multiSet([
        [KEY_ACCESS, tokens.accessToken],
        [KEY_REFRESH, tokens.refreshToken],
      ]);
      set({
        status: 'authenticated',
        user,
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        tokens: { accessToken: tokens.accessToken, refreshToken: tokens.refreshToken },
      });
      return true;
    } catch {
      return false;
    }
  },
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toFailure(err: unknown): AuthFailure {
  if (err instanceof Error) {
    const msg = err.message.toLowerCase();
    if (msg.includes('invalid credentials') || msg.includes('unauthorized') || msg.includes('invalid user credentials')) {
      return { field: 'credentials', message: 'Invalid email or password.' };
    }
    if (msg.includes('email') && msg.includes('already')) {
      return { field: 'email', message: 'An account with this email already exists.' };
    }
    if (msg.includes('username') && msg.includes('already')) {
      return { field: 'username', message: 'This username is taken.' };
    }
    return { field: 'general', message: err.message };
  }
  return { field: 'general', message: 'Something went wrong. Please try again.' };
}
