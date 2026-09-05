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

interface FeedStore {
  posts: Blipp[];
  sort: FeedSort;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;

  setSort: (sort: FeedSort) => void;
  loadFeed: (viewerId?: string | null) => Promise<void>;
  refresh: (viewerId?: string | null) => Promise<void>;
  toggleLike: (postId: string) => void;
}

export const useFeedStore = create<FeedStore>((set, get) => ({
  posts: [],
  sort: 'newest',
  isLoading: false,
  isRefreshing: false,
  error: null,

  setSort(sort) {
    set({ sort });
    get().loadFeed();
  },

  async loadFeed(_viewerId) {
    const { sort } = get();
    set({ isLoading: true, error: null });

    try {
      const response = await blippApi.getFeed();
      const serverItems = response?.items || [];

      const mapped: Blipp[] = serverItems.map((item, idx) => {
        const standardUrl = item.audio_variants?.standard || item.audio_url || '';
        return {
          id: item.blipp_id,
          title: item.title,
          author: 'Creator',
          authorId: item.creator_id,
          duration: item.duration_seconds || 30,
          audio_url: item.audio_url,
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

      const sorted = mapped.sort((a, b) => {
        if (sort === 'newest') {
          return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
        }
        return b.listenCount - a.listenCount;
      });

      set({ posts: sorted, isLoading: false });
    } catch (err) {
      console.warn('Failed to load blipp feed from backend:', err);
      set({ isLoading: false, error: 'Could not load feed from server.' });
    }
  },

  async refresh(viewerId) {
    set({ isRefreshing: true });
    await get().loadFeed(viewerId);
    set({ isRefreshing: false });
  },

  toggleLike(postId) {
    set((state) => ({
      posts: state.posts.map((p) =>
        p.id === postId
          ? { ...p, isLiked: !p.isLiked, likeCount: p.likeCount + (p.isLiked ? -1 : 1) }
          : p,
      ),
    }));
  },
}));
