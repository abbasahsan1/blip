import { create } from 'zustand';
import type { Blipp, FeedSort } from '../types';

// ─── Feed Posts ──────────────────────────────────────────────────────────────
// Posts are consumed directly as returned by the server feed contract.
// No client-side ad interleaving (e.g. index % 5 -> inject ad) is permitted;
// any sponsored/ad units are served directly in the API feed stream.

const INITIAL_POSTS: Blipp[] = [
  {
    id: '1',
    title: 'The Art of Deliberate Practice',
    author: 'Tim Ferriss',
    authorId: 'u1',
    duration: 318, // 5:18
    audio_url: 'https://example.com/audio/1/master.mp3',
    audio_variants: {
      low: 'https://example.com/audio/1/low.mp3',
      standard: 'https://example.com/audio/1/standard.mp3',
      high: 'https://example.com/audio/1/high.mp3',
    },
    audioUrl: 'https://example.com/audio/1/master.mp3',
    coverGradient: ['#6366f1', '#8b5cf6'],
    listenCount: 12400,
    likeCount: 891,
    sourceName: 'The Tim Ferriss Show',
    sourceType: 'podcast',
    tags: ['productivity', 'mindset'],
    createdAt: new Date(Date.now() - 3 * 3600 * 1000).toISOString(),
  },
  {
    id: '2',
    title: 'First Principles Thinking',
    author: 'Lex Fridman',
    authorId: 'u2',
    duration: 247,
    audio_url: 'https://example.com/audio/2/master.mp3',
    audio_variants: {
      low: 'https://example.com/audio/2/low.mp3',
      standard: 'https://example.com/audio/2/standard.mp3',
      high: 'https://example.com/audio/2/high.mp3',
    },
    audioUrl: 'https://example.com/audio/2/master.mp3',
    coverGradient: ['#0f172a', '#1e3a5f'],
    listenCount: 8900,
    likeCount: 672,
    sourceName: 'Lex Fridman Podcast',
    sourceType: 'podcast',
    tags: ['philosophy', 'science'],
    createdAt: new Date(Date.now() - 6 * 3600 * 1000).toISOString(),
  },
  {
    id: '3',
    title: 'How the Brain Processes Audio',
    author: 'Andrew Huberman',
    authorId: 'u3',
    duration: 192,
    audio_url: 'https://example.com/audio/3/master.mp3',
    audio_variants: {
      low: 'https://example.com/audio/3/low.mp3',
      standard: 'https://example.com/audio/3/standard.mp3',
      high: 'https://example.com/audio/3/high.mp3',
    },
    audioUrl: 'https://example.com/audio/3/master.mp3',
    coverGradient: ['#064e3b', '#065f46'],
    listenCount: 21300,
    likeCount: 1840,
    sourceName: 'Huberman Lab',
    sourceType: 'podcast',
    tags: ['neuroscience', 'health'],
    createdAt: new Date(Date.now() - 12 * 3600 * 1000).toISOString(),
  },
  {
    id: '4',
    title: 'Naval on Wealth and Happiness',
    author: 'Naval Ravikant',
    authorId: 'u4',
    duration: 404,
    audio_url: 'https://example.com/audio/4/master.mp3',
    audio_variants: {
      low: 'https://example.com/audio/4/low.mp3',
      standard: 'https://example.com/audio/4/standard.mp3',
      high: 'https://example.com/audio/4/high.mp3',
    },
    audioUrl: 'https://example.com/audio/4/master.mp3',
    coverGradient: ['#78350f', '#92400e'],
    listenCount: 54200,
    likeCount: 4210,
    sourceName: 'The Knowledge Project',
    sourceType: 'interview',
    tags: ['philosophy', 'wealth'],
    createdAt: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
  },
  {
    id: '5',
    title: 'The Power of Deep Work',
    author: 'Cal Newport',
    authorId: 'u5',
    duration: 285,
    audio_url: 'https://example.com/audio/5/master.mp3',
    audio_variants: {
      low: 'https://example.com/audio/5/low.mp3',
      standard: 'https://example.com/audio/5/standard.mp3',
      high: 'https://example.com/audio/5/high.mp3',
    },
    audioUrl: 'https://example.com/audio/5/master.mp3',
    coverGradient: ['#1e1b4b', '#312e81'],
    listenCount: 9800,
    likeCount: 756,
    sourceName: 'Deep Questions',
    sourceType: 'podcast',
    tags: ['productivity', 'focus'],
    createdAt: new Date(Date.now() - 36 * 3600 * 1000).toISOString(),
  },
];

// ─── Store ────────────────────────────────────────────────────────────────────

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
  sort: 'most_listened',
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

    // Simulate network delay for realistic loading state
    await new Promise((r) => setTimeout(r, 400));

    // Consumes items directly without client-side ad interleaving
    const items = [...INITIAL_POSTS];

    const sorted = items.sort((a, b) => {
      if (sort === 'newest') {
        return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      }
      return b.listenCount - a.listenCount;
    });

    set({ posts: sorted, isLoading: false });
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
