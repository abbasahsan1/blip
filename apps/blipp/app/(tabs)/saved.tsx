import React, { useCallback, useEffect, useState, useRef } from 'react';
import {
  ActivityIndicator,
  Animated,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import {
  BookmarkMark,
  PlayMark,
  PauseMark,
  AudioReelMark,
} from '@/components/common/Icons';
import { AudioReel } from '@/components/audio/AudioReel';
import { api, resolvePublicAudioUrl } from '@/lib/api';
import { useSessionStore } from '@/lib/store/sessionStore';
import type { BlippItem } from '@/lib/types';

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function SavedScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const accessToken = useSessionStore((s) => s.accessToken);

  const [items, setItems] = useState<BlippItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Active playing item for inline preview
  const [activeInlineId, setActiveInlineId] = useState<string | null>(null);
  const audioRef = useRef<any>(null);

  // Active item for full reel modal
  const [activeReelItem, setActiveReelItem] = useState<BlippItem | null>(null);

  const loadSaved = useCallback(async () => {
    if (!accessToken) {
      setItems([]);
      return;
    }
    try {
      const saved = await api.getSavedBlipps();
      setItems(saved || []);
    } catch {
      setItems([]);
    }
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      setIsLoading(false);
      setItems([]);
      return;
    }
    setIsLoading(true);
    void loadSaved().finally(() => setIsLoading(false));
  }, [accessToken, loadSaved]);

  const onRefresh = async () => {
    if (!accessToken) return;
    setIsRefreshing(true);
    await loadSaved();
    setIsRefreshing(false);
  };

  const handleUnsave = async (blippId: string) => {
    setItems((prev) => prev.filter((it) => it.id !== blippId && it.blipp_id !== blippId));
    try {
      await api.unsaveBlipp(blippId);
    } catch {
      void loadSaved();
    }
  };

  const toggleInlinePlay = (item: BlippItem) => {
    const id = item.blipp_id || item.id;
    if (activeInlineId === id) {
      if (audioRef.current) {
        audioRef.current.pause?.();
      }
      setActiveInlineId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause?.();
      audioRef.current = null;
    }

    const url = resolvePublicAudioUrl(item.audio_variants?.standard || item.audio_url || item.audioUrl || '');
    if (!url) return;

    if (typeof window !== 'undefined' && typeof Audio !== 'undefined') {
      try {
        const nextAudio = new Audio(url);
        nextAudio.play().catch(() => {});
        nextAudio.onended = () => setActiveInlineId(null);
        audioRef.current = nextAudio;
        setActiveInlineId(id);
      } catch {
        setActiveInlineId(null);
      }
    } else {
      // Toggle state preview indicator for native mobile
      setActiveInlineId(id);
    }
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause?.();
        audioRef.current = null;
      }
    };
  }, []);

  const renderItem = ({ item, index }: { item: BlippItem; index: number }) => {
    const id = item.blipp_id || item.id;
    const isPlayingInline = activeInlineId === id;

    // Generate static waveform bar heights for waveform snippet
    const barHeights = [40, 75, 55, 90, 60, 85, 45, 95, 70, 50, 80, 65, 90, 45, 60];

    return (
      <Pressable
        style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
        onPress={() => {
          if (audioRef.current) {
            audioRef.current.pause?.();
            setActiveInlineId(null);
          }
          setActiveReelItem(item);
        }}
        accessibilityRole="button"
        accessibilityLabel={`Stashed blipp: ${item.title}`}
        testID={`saved-item-${id}`}
      >
        {/* Top Header: Creator Avatar & Unstash Ribbon */}
        <View style={styles.cardHeaderRow}>
          <View style={styles.creatorBadge}>
            <View style={styles.avatarCircle}>
              <Text style={styles.avatarInitial}>
                {(item.author || 'C').charAt(0).toUpperCase()}
              </Text>
            </View>
            <View style={styles.creatorTextWrap}>
              <Text style={styles.creatorName} numberOfLines={1}>
                {item.author || 'Creator'}
              </Text>
              <Text style={styles.broadcastDate}>
                {item.createdAt ? new Date(item.createdAt).toLocaleDateString() : 'Archived'}
              </Text>
            </View>
          </View>

          {/* Unstash Ribbon Button */}
          <Pressable
            style={({ pressed }) => [
              styles.unsaveBtn,
              pressed && styles.btnPressed,
            ]}
            onPress={(e) => {
              e.stopPropagation?.();
              handleUnsave(id);
            }}
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            accessibilityRole="button"
            accessibilityLabel="Remove from stash"
            testID={`unsave-button-${id}`}
          >
            <BookmarkMark size={20} color={PALETTE.amber} filled={true} />
          </Pressable>
        </View>

        {/* Title */}
        <Text style={styles.cardTitle} numberOfLines={2}>
          {item.title}
        </Text>

        {/* Waveform Preview Snippet */}
        <View style={styles.waveformSnippetContainer}>
          <View style={styles.waveformBars}>
            {barHeights.map((heightPercent, idx) => (
              <View
                key={idx}
                style={[
                  styles.waveformSnippetBar,
                  {
                    height: `${heightPercent}%`,
                    backgroundColor: isPlayingInline
                      ? PALETTE.accent
                      : idx < 6
                      ? 'rgba(124, 58, 237, 0.6)'
                      : 'rgba(255, 255, 255, 0.18)',
                  },
                ]}
              />
            ))}
          </View>
        </View>

        {/* Card Footer: Duration Pill & Instant Inline Playback */}
        <View style={styles.cardFooter}>
          <View style={styles.durationPill}>
            <View style={styles.durationDot} />
            <Text style={styles.durationText}>
              {formatDuration(item.duration_seconds || item.duration || 0)}
            </Text>
          </View>

          <Text style={styles.tapToPlayHint}>Tap to stream reel</Text>

          {/* Instant Inline Playback Button */}
          <Pressable
            style={({ pressed }) => [
              styles.inlinePlayBtn,
              isPlayingInline && styles.inlinePlayBtnActive,
              pressed && styles.btnPressed,
            ]}
            onPress={(e) => {
              e.stopPropagation?.();
              toggleInlinePlay(item);
            }}
            accessibilityRole="button"
            accessibilityLabel={isPlayingInline ? 'Pause preview' : 'Play audio preview'}
            testID={`inline-play-${id}`}
          >
            {isPlayingInline ? (
              <PauseMark size={16} color="#FFFFFF" />
            ) : (
              <PlayMark size={16} color="#FFFFFF" />
            )}
          </Pressable>
        </View>
      </Pressable>
    );
  };

  if (!accessToken) {
    return (
      <View style={styles.root}>
        <View style={[styles.header, { paddingTop: insets.top + 18 }]}>
          <Text style={styles.headerTitle}>My Stash 🎧</Text>
          <Text style={styles.headerSubtitle}>
            Your bookmarked frequencies and saved broadcast moments
          </Text>
        </View>
        <View style={styles.authGuardContainer}>
          <View style={styles.authGuardIconCircle}>
            <BookmarkMark size={44} color={PALETTE.amber} filled />
          </View>
          <Text style={styles.authGuardHeading}>Sign in to access your Stash</Text>
          <Text style={styles.authGuardSubtext}>
            Log in to stream bookmarked broadcasts and listen to your saved clips offline or on-demand.
          </Text>
          <Pressable
            style={({ pressed }) => [
              styles.authGuardBtn,
              pressed && styles.authGuardBtnPressed,
            ]}
            onPress={() => router.push('/(auth)/sign-in' as any)}
            accessibilityRole="button"
            accessibilityLabel="Sign in to view saved Blipps"
            testID="saved-signin-button"
          >
            <Text style={styles.authGuardBtnText}>Sign In to Blipp</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {/* Header: Rebranded to My Stash 🎧 */}
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <View style={styles.headerTitleRow}>
          <Text style={styles.headerTitle}>My Stash 🎧</Text>
          {items.length > 0 && (
            <View style={styles.stashCountBadge}>
              <Text style={styles.stashCountText}>{items.length}</Text>
            </View>
          )}
        </View>
        <Text style={styles.headerSubtitle}>
          Curated collection of your bookmarked audio reels
        </Text>
      </View>

      {isLoading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={PALETTE.accent} />
          <Text style={styles.loadingText}>Fetching your stashed tracks...</Text>
        </View>
      ) : items.length === 0 ? (
        <View style={styles.emptyContainer}>
          <View style={styles.emptyIconCircle}>
            <AudioReelMark size={48} color={PALETTE.textMuted} />
          </View>
          <Text style={styles.emptyHeading}>Your Stash is Empty</Text>
          <Text style={styles.emptySubheading}>
            Tap the bookmark ribbon on any broadcast in your feed to save it here for quick listening.
          </Text>
          <Pressable
            style={styles.exploreBtn}
            onPress={() => router.push('/' as any)}
          >
            <Text style={styles.exploreBtnText}>Explore Feed 🔥</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(it) => it.blipp_id || it.id}
          renderItem={renderItem}
          contentContainerStyle={[
            styles.listContent,
            { paddingBottom: insets.bottom + 90 },
          ]}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={onRefresh}
              tintColor={PALETTE.accent}
              colors={[PALETTE.accent]}
            />
          }
        />
      )}

      {/* Full Audio Reel Modal for Selected Stashed Item */}
      <Modal
        visible={Boolean(activeReelItem)}
        animationType="slide"
        onRequestClose={() => setActiveReelItem(null)}
      >
        <View style={styles.reelModalContainer}>
          {activeReelItem && (
            <AudioReel
              item={activeReelItem as any}
              isActive={true}
              height={760}
              onLike={() => {
                setActiveReelItem((prev) =>
                  prev ? { ...prev, isLiked: !prev.isLiked } : null,
                );
              }}
            />
          )}
          <Pressable
            style={[styles.closeReelBtn, { top: insets.top + 12 }]}
            onPress={() => setActiveReelItem(null)}
            accessibilityRole="button"
            accessibilityLabel="Close broadcast reel"
          >
            <Text style={styles.closeReelBtnText}>✕ Close</Text>
          </Pressable>
        </View>
      </Modal>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 16,
    backgroundColor: PALETTE.surface,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 4,
  },
  headerTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 24,
    color: PALETTE.primary,
    letterSpacing: -0.5,
  },
  stashCountBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
    backgroundColor: PALETTE.accentDim,
    borderWidth: 1,
    borderColor: PALETTE.accent,
  },
  stashCountText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: PALETTE.accent,
  },
  headerSubtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },

  // List & Cards
  listContent: {
    padding: 16,
    gap: 14,
  },
  card: {
    backgroundColor: PALETTE.card,
    borderRadius: 18,
    padding: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 4,
  },
  cardPressed: {
    backgroundColor: PALETTE.cardHover,
    transform: [{ scale: 0.99 }],
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  creatorBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
  },
  avatarCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 15,
    color: '#FFFFFF',
  },
  creatorTextWrap: {
    flex: 1,
  },
  creatorName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.primary,
  },
  broadcastDate: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  unsaveBtn: {
    padding: 6,
  },
  btnPressed: {
    opacity: 0.7,
  },
  cardTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 16,
    color: PALETTE.primary,
    lineHeight: 22,
    marginBottom: 12,
  },

  // Waveform Preview Snippet
  waveformSnippetContainer: {
    height: 36,
    backgroundColor: PALETTE.surface,
    borderRadius: 10,
    paddingHorizontal: 10,
    justifyContent: 'center',
    marginBottom: 12,
    borderWidth: 1,
    borderColor: PALETTE.borderSubtle,
  },
  waveformBars: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: '100%',
  },
  waveformSnippetBar: {
    width: 3.5,
    borderRadius: 2,
  },

  // Footer & Inline Play
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  durationPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  durationDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: PALETTE.lime,
  },
  durationText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: PALETTE.primary,
  },
  tapToPlayHint: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  inlinePlayBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.5,
    shadowRadius: 6,
  },
  inlinePlayBtnActive: {
    backgroundColor: PALETTE.magenta,
  },

  // Auth Guard
  authGuardContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  authGuardIconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: PALETTE.amberDim,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
    borderWidth: 1,
    borderColor: PALETTE.amber,
  },
  authGuardHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 20,
    color: PALETTE.primary,
    marginBottom: 8,
    textAlign: 'center',
  },
  authGuardSubtext: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 24,
  },
  authGuardBtn: {
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 24,
    backgroundColor: PALETTE.accent,
  },
  authGuardBtnPressed: {
    opacity: 0.8,
  },
  authGuardBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: '#FFFFFF',
  },

  // Empty State & Loading
  centerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  loadingText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    marginTop: 12,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  emptyIconCircle: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: PALETTE.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  emptyHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 19,
    color: PALETTE.primary,
    marginBottom: 8,
  },
  emptySubheading: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 19,
    marginBottom: 20,
  },
  exploreBtn: {
    paddingHorizontal: 22,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  exploreBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.primary,
  },

  // Reel Modal
  reelModalContainer: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  closeReelBtn: {
    position: 'absolute',
    right: 18,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 18,
    backgroundColor: 'rgba(17, 19, 27, 0.85)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    zIndex: 20,
  },
  closeReelBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: '#FFFFFF',
  },
});
