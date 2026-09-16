import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Dimensions,
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AudioReel } from '@/components/audio/AudioReel';
import { StoriesTray } from '@/components/stories/StoriesTray';
import { AcousticDeckMark } from '@/components/common/Icons';
import { useFeedStore } from '@/lib/store/feedStore';
import { useSessionStore } from '@/lib/store/sessionStore';
import { theme } from '@/lib/theme';
import type { AudioPost, FeedSort } from '@/lib/types';

const SORTS: { value: FeedSort; label: string }[] = [
  { value: 'most_listened', label: 'Trending' },
  { value: 'newest', label: 'Newest' },
];

export default function FeedScreen() {
  const insets = useSafeAreaInsets();

  const posts = useFeedStore((s) => s.posts);
  const cursor = useFeedStore((s) => s.cursor);
  const sort = useFeedStore((s) => s.sort);
  const isLoading = useFeedStore((s) => s.isLoading);
  const isRefreshing = useFeedStore((s) => s.isRefreshing);
  const error = useFeedStore((s) => s.error);
  const setSort = useFeedStore((s) => s.setSort);
  const fetchFeed = useFeedStore((s) => s.fetchFeed);
  const refresh = useFeedStore((s) => s.refresh);
  const toggleLike = useFeedStore((s) => s.toggleLike);
  const toggleSave = useFeedStore((s) => s.toggleSave);
  const toggleFollow = useFeedStore((s) => s.toggleFollow);

  const userId = useSessionStore((s) => s.user?.id ?? null);

  const [activeIndex, setActiveIndex] = useState(0);
  const [feedHeight, setFeedHeight] = useState(0);
  const listRef = useRef<FlatList<AudioPost>>(null);

  useEffect(() => {
    void refresh(userId);
  }, []);

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      if (feedHeight > 0) {
        const idx = Math.round(e.nativeEvent.contentOffset.y / feedHeight);
        setActiveIndex(idx);
      }
    },
    [feedHeight],
  );

  const handleAutoSkip = useCallback(
    (index: number) => {
      if (index < posts.length - 1) {
        listRef.current?.scrollToIndex({ index: index + 1, animated: true });
      }
    },
    [posts.length],
  );

  const loadMore = useCallback(() => {
    if (cursor && !isLoading && !error) {
      void fetchFeed(cursor);
    }
  }, [cursor, fetchFeed, isLoading, error]);

  const renderItem = useCallback(
    ({ item, index }: { item: AudioPost; index: number }) => (
      <AudioReel
        post={item}
        isActive={index === activeIndex}
        height={feedHeight}
        onLike={() => toggleLike(item.id)}
        onSave={() => toggleSave(item.id)}
        onFollow={() => { if (item.creator_id) toggleFollow(item.creator_id); }}
        onAutoSkip={() => handleAutoSkip(index)}
        feedItems={posts}
        activeIndex={index}
        shouldLoad={Math.abs(index - activeIndex) <= 1}
      />
    ),
    [activeIndex, handleAutoSkip, posts, toggleLike, feedHeight],
  );

  if (error && posts.length === 0) {
    return (
      <View style={[styles.root, styles.centerContent]}>
        <Text style={styles.errorText}>{error}</Text>
        <Pressable style={styles.retryButton} onPress={() => refresh(userId)}>
          <Text style={styles.retryButtonText}>Retry</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.root} onLayout={(e) => setFeedHeight(e.nativeEvent.layout.height)}>
      {/* Quiet Header */}
      <View
        style={[
          styles.headerContainer,
          { paddingTop: insets.top },
        ]}
      >
        <View style={styles.header}>
          <Text style={styles.headerLogo}>blipp</Text>
          <View style={styles.sortChips}>
            {SORTS.map((s) => (
              <Pressable
                key={s.value}
                style={[styles.chip, sort === s.value && styles.chipActive]}
                onPress={() => setSort(s.value)}
                accessibilityRole="button"
                accessibilityState={{ selected: sort === s.value }}
              >
                <Text style={[styles.chipText, sort === s.value && styles.chipTextActive]}>
                  {s.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </View>

      {isLoading && posts.length === 0 ? (
        <View style={[styles.root, styles.centerContent]}>
          <ActivityIndicator size="large" color={theme.colors.primary} />
          <Text style={styles.loadingText}>Loading broadcasts...</Text>
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={posts}
          keyExtractor={(p) => p.id}
          renderItem={renderItem}
          onEndReached={loadMore}
          onEndReachedThreshold={0.7}
          onScroll={onScroll}
          scrollEventThrottle={16}
          pagingEnabled={true}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={() => refresh(userId)}
              tintColor={theme.colors.primary}
              colors={[theme.colors.primary]}
              progressViewOffset={insets.top + 60}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <View style={styles.emptyIconWrap}>
                <AcousticDeckMark size={48} color={theme.colors.textMuted} />
              </View>
              <Text style={styles.emptyHeading}>No broadcasts available</Text>
              <Text style={styles.emptySub}>
                The frequency is quiet. Why not upload a track or pull to refresh?
              </Text>
              <Pressable style={styles.retryButton} onPress={() => refresh(userId)}>
                <Text style={styles.retryButtonText}>Refresh</Text>
              </Pressable>
            </View>
          }
          getItemLayout={(_data, index) => ({
            length: feedHeight,
            offset: feedHeight * index,
            index,
          })}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  centerContent: {
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.xxl,
  },
  headerContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 20,
    backgroundColor: 'rgba(10, 10, 10, 0.4)', // subtle gradient equivalent
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.xl,
    paddingVertical: theme.spacing.md,
  },
  headerLogo: {
    ...theme.typography.display,
    color: theme.colors.text,
    letterSpacing: -1,
  },
  sortChips: {
    flexDirection: 'row',
    gap: theme.spacing.sm,
  },
  chip: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  chipActive: {
    borderBottomWidth: 2,
    borderBottomColor: theme.colors.primary,
  },
  chipText: {
    ...theme.typography.metadata,
    color: theme.colors.textMuted,
  },
  chipTextActive: {
    ...theme.typography.metadata,
    color: theme.colors.primary,
  },
  loadingText: {
    ...theme.typography.body,
    color: theme.colors.textMuted,
    marginTop: theme.spacing.lg,
  },
  errorText: {
    ...theme.typography.body,
    color: theme.colors.error,
    textAlign: 'center',
    marginBottom: theme.spacing.lg,
  },
  retryButton: {
    backgroundColor: theme.colors.surface,
    paddingHorizontal: theme.spacing.xl,
    paddingVertical: theme.spacing.md,
    borderRadius: theme.radius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    marginTop: theme.spacing.lg,
  },
  retryButtonText: {
    ...theme.typography.button,
    color: theme.colors.text,
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: theme.spacing.xxxl,
    paddingTop: 200,
  },
  emptyIconWrap: {
    marginBottom: theme.spacing.xl,
    opacity: 0.6,
  },
  emptyHeading: {
    ...theme.typography.title,
    color: theme.colors.text,
    marginBottom: theme.spacing.sm,
    textAlign: 'center',
  },
  emptySub: {
    ...theme.typography.body,
    color: theme.colors.textMuted,
    textAlign: 'center',
  },
});
