import { create } from 'zustand';
import { blippApi } from '../api';
import type { Blipp, FeedSort } from '../types';

const GRADIENTS: [string, string][] = [
  ['#2563eb', '#8b5cf6'],
  ['#6366f1', '#a855f7'],
  ['#0f172a', '#1e3a5f'],
  ['#064e3b', '#065f46'],
  ['#78350f', '#92400e'],
  ['#1e1b4b', '#312e81'],
];

export interface FeedState {
  items: Blipp[];
  cursor: string | null;
  isLoading: boolean;
  error: string | null;
  fetchFeed: (cursor?: string | null) => Promise<void>;
  refreshFeed: () => Promise<void>;

  // Compatibility aliases for UI components
  posts: Blipp[];
  isRefreshing: boolean;
  sort: FeedSort;
  setSort: (sort: FeedSort) => void;
  loadFeed: (viewerId?: string | null) => Promise<void>;
  refresh: (viewerId?: string | null) => Promise<void>;
  toggleLike: (postId: string) => void;
}

export const useFeedStore = create<FeedState>((set, get) => ({
  items: [],
  posts: [],
  cursor: null,
  isLoading: false,
  isRefreshing: false,
  error: null,
  sort: 'newest',

  async fetchFeed(cursor?: string | null) {
    set({ isLoading: true, error: null });
    try {
      const res = await blippApi.getFeed();
      const serverItems = res.items || [];

      const nextCursor = res.next_cursor ?? null;

      const mapped: Blipp[] = serverItems.map((item, idx: number) => {
        const standardUrl = item.audio_variants?.standard || item.audio_url || '';
        return {
          id: item.blipp_id,
          blipp_id: item.blipp_id,
          title: item.title,
          description: item.description,
          author: item.display_name || item.author || (item.username ? `@${item.username}` : 'Creator'),
          authorId: item.creator_id,
          creator_id: item.creator_id,
          duration: item.duration_seconds || 30,
          duration_seconds: item.duration_seconds || 30,
          audio_url: item.audio_url || standardUrl,
          audio_variants: {
            standard: standardUrl,
            low: item.audio_variants?.low || standardUrl,
            high: item.audio_variants?.high || standardUrl,
          },
          audioUrl: standardUrl,
          coverGradient: GRADIENTS[idx % GRADIENTS.length],
          listenCount: 0,
          likeCount: 0,
          isLiked: false,
          createdAt: new Date().toISOString(),
        };
      });

      set((state) => {
        const updated = cursor ? [...state.items, ...mapped] : mapped;
        return {
          items: updated,
          posts: updated,
          cursor: nextCursor,
          isLoading: false,
        };
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Could not load feed from server.';
      set({ isLoading: false, error: msg });
    }
  },

  async refreshFeed() {
    set({ isRefreshing: true });
    await get().fetchFeed(null);
    set({ isRefreshing: false });
  },

  // Backwards-compatible aliases
  setSort(sort: FeedSort) {
    set({ sort });
    get().refreshFeed();
  },

  async loadFeed(_viewerId?: string | null) {
    await get().fetchFeed(null);
  },

  async refresh(_viewerId?: string | null) {
    await get().refreshFeed();
  },

  toggleLike(postId: string) {
    set((state) => {
      const updated = state.items.map((p) =>
        p.id === postId
          ? { ...p, isLiked: !p.isLiked, likeCount: p.likeCount + (p.isLiked ? -1 : 1) }
          : p,
      );
      return { items: updated, posts: updated };
    });
  },
}));
