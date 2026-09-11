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
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AudioReel } from '@/components/audio/AudioReel';
import { StoriesTray } from '@/components/stories/StoriesTray';
import { AcousticDeckMark } from '@/components/common/Icons';
import { useFeedStore } from '@/lib/store/feedStore';
import { useSessionStore } from '@/lib/store/sessionStore';
import { PALETTE } from '@/lib/palette';
import type { AudioPost, FeedSort } from '@/lib/types';

const { height: WINDOW_HEIGHT, width: WINDOW_WIDTH } = Dimensions.get('window');

const SORTS: { value: FeedSort; label: string }[] = [
  { value: 'most_listened', label: 'Trending' },
  { value: 'newest', label: 'Newest' },
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

  const [activeIndex, setActiveIndex] = useState(0);
  const listRef = useRef<FlatList<AudioPost>>(null);

  useEffect(() => {
    void refresh(userId);
  }, []);

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const idx = Math.round(e.nativeEvent.contentOffset.y / WINDOW_HEIGHT);
      setActiveIndex(idx);
    },
    [],
  );

  const handleAutoSkip = useCallback(
    (index: number) => {
      if (index < posts.length - 1) {
        listRef.current?.scrollToIndex({ index: index + 1, animated: true });
      }
    },
    [posts.length],
  );

  const renderItem = useCallback(
    ({ item, index }: { item: AudioPost; index: number }) => (
      <AudioReel
        post={item}
        isActive={index === activeIndex}
        height={WINDOW_HEIGHT}
        onLike={() => toggleLike(item.id)}
        onAutoSkip={() => handleAutoSkip(index)}
        feedItems={posts}
        activeIndex={index}
      />
    ),
    [activeIndex, handleAutoSkip, posts, toggleLike],
  );

  return (
    <View style={styles.root}>
      {/* Studio Header Bar & Stories Tray */}
      <View
        style={[
          styles.headerContainer,
          { paddingTop: insets.top + 10 },
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
        <StoriesTray />
      </View>

      {/* Structured Acoustic Loading Skeletons */}
      {isLoading && posts.length === 0 ? (
        <View style={styles.loadingState}>
          {[0, 1].map((i) => (
            <View key={i} style={styles.skeletonDeck}>
              <View style={styles.skeletonTag} />
              <View style={styles.skeletonTitle} />
              <View style={styles.skeletonAuthor} />
              <View style={styles.skeletonWaveform} />
              <View style={styles.skeletonControls}>
                <View style={styles.skeletonBtn} />
                <View style={styles.skeletonMeta} />
              </View>
            </View>
          ))}
        </View>
      ) : (
        <FlatList
          ref={listRef}
          data={posts}
          keyExtractor={(p) => p.id}
          renderItem={renderItem}
          onScroll={onScroll}
          scrollEventThrottle={16}
          pagingEnabled={true}
          snapToInterval={WINDOW_HEIGHT}
          snapToAlignment="start"
          decelerationRate="fast"
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={() => refresh(userId)}
              tintColor={PALETTE.primary}
              colors={[PALETTE.primary]}
              progressViewOffset={insets.top + 60}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <View style={styles.emptyIconWrap}>
                <AcousticDeckMark size={48} color={PALETTE.textMuted} />
              </View>
              <Text style={styles.emptyHeading}>No broadcasts available</Text>
              <Text style={styles.emptySub}>
                The frequency is quiet. Switch tabs to upload an audio track or pull to refresh.
              </Text>
            </View>
          }
          getItemLayout={(_data, index) => ({
            length: WINDOW_HEIGHT,
            offset: WINDOW_HEIGHT * index,
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
  headerContainer: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 20,
    backgroundColor: 'transparent',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingBottom: 8,
  },
  headerLogo: {
    fontFamily: 'Sora_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    letterSpacing: -1,
  },
  sortChips: {
    flexDirection: 'row',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: PALETTE.border,
    backgroundColor: PALETTE.surface,
    minHeight: 30,
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: PALETTE.accentDim,
    borderColor: PALETTE.accent,
  },
  chipText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  chipTextActive: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    color: PALETTE.accent,
  },
  loadingState: {
    flex: 1,
    paddingHorizontal: 24,
    paddingTop: 140,
    gap: 32,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
  },
  skeletonDeck: {
    gap: 12,
    paddingVertical: 16,
  },
  skeletonTag: {
    width: 90,
    height: 18,
    borderRadius: 4,
    backgroundColor: PALETTE.surface,
  },
  skeletonTitle: {
    width: '80%',
    height: 28,
    borderRadius: 6,
    backgroundColor: PALETTE.surface,
  },
  skeletonAuthor: {
    width: 140,
    height: 16,
    borderRadius: 4,
    backgroundColor: PALETTE.surface,
    opacity: 0.7,
  },
  skeletonWaveform: {
    height: 36,
    borderRadius: 4,
    backgroundColor: PALETTE.surface,
    opacity: 0.5,
  },
  skeletonControls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  skeletonBtn: {
    width: 48,
    height: 48,
    borderRadius: 8,
    backgroundColor: PALETTE.surface,
  },
  skeletonMeta: {
    width: 120,
    height: 16,
    borderRadius: 4,
    backgroundColor: PALETTE.surface,
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
    paddingTop: 200,
  },
  emptyIconWrap: {
    marginBottom: 20,
    opacity: 0.6,
  },
  emptyHeading: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 18,
    color: PALETTE.text,
    marginBottom: 8,
    textAlign: 'center',
  },
  emptySub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
    textAlign: 'center',
    lineHeight: 22,
    maxWidth: 340,
  },
});
