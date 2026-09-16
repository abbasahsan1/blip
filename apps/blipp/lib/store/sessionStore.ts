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
  requestOtp: (email: string) => Promise<boolean>;
  verifyOtp: (email: string, code: string) => Promise<void>;
  signInWithOAuth: (provider: 'google' | 'apple', idToken?: string, code?: string) => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
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

  async requestOtp(email: string) {
    set({ isSubmitting: true, error: null });
    try {
      await authApi.requestOtp(email);
      set({ isSubmitting: false });
      return true;
    } catch (err) {
      set({ isSubmitting: false, error: toFailure(err) });
      return false;
    }
  },

  async verifyOtp(email: string, code: string) {
    set({ isSubmitting: true, error: null });
    try {
      const { tokens, user } = await authApi.verifyOtp(email, code);
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
        isSubmitting: false,
      });
    } catch (err) {
      set({ isSubmitting: false, error: toFailure(err) });
    }
  },

  async signInWithOAuth(provider: 'google' | 'apple', idToken?: string, code?: string) {
    set({ isSubmitting: true, error: null });
    try {
      const { tokens, user } = await authApi.signInWithOAuth(provider, idToken, code);
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
        isSubmitting: false,
      });
    } catch (err) {
      set({ isSubmitting: false, error: toFailure(err) });
    }
  },

  async signInWithEmail(email, password) {
    set({ isSubmitting: true, error: null });
    try {
      const { tokens, user } = await authApi.login({ email, password });
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
        isSubmitting: false,
      });
    } catch (err) {
      const failure = toFailure(err);
      set({ isSubmitting: false, error: failure });
    }
  },

  async signUpWithEmail(username, email, password) {
    set({ isSubmitting: true, error: null });
    try {
      const pwd = password || 'DefaultOtpPassword123!';
      const { tokens, user } = await authApi.register({ username, email, password: pwd });
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
        isSubmitting: false,
      });
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
  if (err instanceof ApiError) {
    const msg = err.message.toLowerCase();
    if (msg.includes('invalid credentials') || msg.includes('unauthorized') || err.status === 401) {
      return { field: 'credentials', message: 'Incorrect email or password.' };
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
