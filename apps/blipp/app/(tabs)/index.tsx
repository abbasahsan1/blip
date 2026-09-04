import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AudioReel } from '@/components/audio/AudioReel';
import { useFeedStore } from '@/lib/store/feedStore';
import { useSessionStore } from '@/lib/store/sessionStore';
import { PALETTE } from '@/lib/palette';
import type { AudioPost, FeedSort } from '@/lib/types';

const SORTS: { value: FeedSort; label: string }[] = [
  { value: 'most_listened', label: 'Trending' },
  { value: 'newest', label: 'New' },
];

export default function FeedScreen() {
  const insets = useSafeAreaInsets();

  const posts = useFeedStore((s) => s.posts);
  const sort = useFeedStore((s) => s.sort);
  const isLoading = useFeedStore((s) => s.isLoading);
  const isRefreshing = useFeedStore((s) => s.isRefreshing);
  const setSort = useFeedStore((s) => s.setSort);
  const refresh = useFeedStore((s) => s.refresh);
  const toggleLike = useFeedStore((s) => s.toggleLike);

  const userId = useSessionStore((s) => s.user?.id ?? null);

  const [pageHeight, setPageHeight] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<FlatList<AudioPost>>(null);

  useEffect(() => {
    void refresh(userId);
  }, []);

  const onLayout = useCallback((e: LayoutChangeEvent) => {
    setPageHeight(e.nativeEvent.layout.height);
  }, []);

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      if (pageHeight === 0) return;
      const idx = Math.round(e.nativeEvent.contentOffset.y / pageHeight);
      setActiveIndex(idx);
    },
    [pageHeight],
  );

  const renderItem = useCallback(
    ({ item, index }: { item: AudioPost; index: number }) => (
      <AudioReel
        post={item}
        isActive={index === activeIndex}
        height={pageHeight}
        onLike={() => toggleLike(item.id)}
      />
    ),
    [activeIndex, pageHeight, toggleLike],
  );

  return (
    <View style={styles.root}>
      {/* Header */}
      <View
        style={[
          styles.header,
          { paddingTop: insets.top + 8 },
        ]}
      >
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

      {/* Loading state */}
      {isLoading && posts.length === 0 ? (
        <View style={styles.loadingState}>
          {[0, 1, 2].map((i) => (
            <View key={i} style={styles.skeleton} />
          ))}
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={posts}
          keyExtractor={(p) => p.id}
          renderItem={renderItem}
          onLayout={onLayout}
          onScroll={onScroll}
          scrollEventThrottle={16}
          pagingEnabled
          showsVerticalScrollIndicator={false}
          snapToInterval={pageHeight || undefined}
          decelerationRate="fast"
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={() => refresh(userId)}
              tintColor={PALETTE.accent}
              colors={[PALETTE.accent]}
            />
          }
          getItemLayout={(_data, index) => ({
            length: pageHeight,
            offset: pageHeight * index,
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
    backgroundColor: PALETTE.bg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingBottom: 12,
    backgroundColor: PALETTE.bg,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.borderSubtle,
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
  },
  headerLogo: {
    fontFamily: 'Inter_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    letterSpacing: -1,
  },
  sortChips: {
    flexDirection: 'row',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: PALETTE.border,
    backgroundColor: 'transparent',
    minHeight: 32,
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: PALETTE.accentDim,
    borderColor: PALETTE.accent,
  },
  chipText: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: PALETTE.textMuted,
  },
  chipTextActive: {
    color: PALETTE.accent,
  },
  loadingState: {
    flex: 1,
    paddingHorizontal: 20,
    paddingTop: 120,
    gap: 16,
  },
  skeleton: {
    height: 200,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    opacity: 0.6,
  },
});
