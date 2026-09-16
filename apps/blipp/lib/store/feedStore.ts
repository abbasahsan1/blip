import { create } from 'zustand';
import { blippApi, likeBlipp, resolvePublicAudioUrl } from '../api';
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
  toggleLike: (postId: string) => Promise<void>;
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
      const res = await blippApi.getFeed(cursor);
      const serverItems = res.items || [];

      const nextCursor = res.next_cursor ?? null;

      const mapped: Blipp[] = serverItems.map((item, idx: number) => {
        const rawStandard = item.audio_variants?.standard || item.audio_url || '';
        const standardUrl = resolvePublicAudioUrl(rawStandard);
        const lowUrl = resolvePublicAudioUrl(item.audio_variants?.low || rawStandard);
        const highUrl = resolvePublicAudioUrl(item.audio_variants?.high || rawStandard);
        const isAd = Boolean(item.is_ad || item.is_sponsored);
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
          audio_url: standardUrl,
          audio_variants: {
            standard: standardUrl,
            low: lowUrl,
            high: highUrl,
          },
          audioUrl: standardUrl,
          coverGradient: GRADIENTS[idx % GRADIENTS.length],
          listenCount: item.listens_count || item.listenCount || 0,
          likeCount: item.likes_count || item.likeCount || 0,
          isLiked: Boolean(item.isLiked || item.is_liked),
          is_ad: isAd,
          is_sponsored: isAd,
          is_saved: Boolean(item.is_saved),
          is_following: Boolean(item.is_following),
          creator: item.creator,
          sponsor: item.sponsor,
          tags: item.tags || [],
          sourceName: item.sourceName,
          createdAt: item.created_at || new Date().toISOString(),
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

  async toggleLike(postId: string) {
    const post = get().items.find((item) => item.id === postId);
    if (!post || post.isLiked) return;

    // Optimistically show the active orange heart, then restore the exact
    // server-facing state if persistence fails.
    set((state) => {
      const updated = state.items.map((item) =>
        item.id === postId
          ? { ...item, isLiked: true, likeCount: item.likeCount + 1 }
          : item,
      );
      return { items: updated, posts: updated };
    });

    try {
      await likeBlipp(postId);
    } catch {
      set((state) => {
        const updated = state.items.map((item) =>
          item.id === postId
            ? { ...item, isLiked: false, likeCount: Math.max(0, item.likeCount - 1) }
            : item,
        );
        return { items: updated, posts: updated };
      });
    }
  },
}));
