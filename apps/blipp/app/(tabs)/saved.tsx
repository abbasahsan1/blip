import React, { useCallback, useEffect, useState } from 'react';
import {
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import {
  BookmarkMark,
  PlayMark,
  PauseMark,
} from '@/components/common/Icons';
import { AudioReel } from '@/components/audio/AudioReel';
import { api, resolvePublicAudioUrl } from '@/lib/api';
import type { BlippItem } from '@/lib/types';

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function SavedScreen() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<BlippItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Active playing item for inline preview
  const [activeInlineId, setActiveInlineId] = useState<string | null>(null);
  const [audioEl, setAudioEl] = useState<HTMLAudioElement | null>(null);

  // Active item for full reel modal
  const [activeReelItem, setActiveReelItem] = useState<BlippItem | null>(null);

  const loadSaved = useCallback(async () => {
    try {
      const saved = await api.getSavedBlipps();
      setItems(saved || []);
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    void loadSaved().finally(() => setIsLoading(false));
  }, [loadSaved]);

  const onRefresh = async () => {
    setIsRefreshing(true);
    await loadSaved();
    setIsRefreshing(false);
  };

  const handleUnsave = async (blippId: string) => {
    // Optimistic removal
    setItems((prev) => prev.filter((it) => it.id !== blippId && it.blipp_id !== blippId));
    try {
      await api.unsaveBlipp(blippId);
    } catch {
      // Reload on failure
      void loadSaved();
    }
  };

  const toggleInlinePlay = (item: BlippItem) => {
    const id = item.blipp_id || item.id;
    if (activeInlineId === id) {
      audioEl?.pause();
      setActiveInlineId(null);
      return;
    }

    if (audioEl) {
      audioEl.pause();
      audioEl.src = '';
    }

    if (typeof window === 'undefined' || typeof Audio === 'undefined') return;

    const url = resolvePublicAudioUrl(item.audio_variants?.standard || item.audio_url || item.audioUrl || '');
    if (!url) return;

    const nextAudio = new Audio(url);
    nextAudio.play().catch(() => {});
    nextAudio.onended = () => setActiveInlineId(null);
    setAudioEl(nextAudio);
    setActiveInlineId(id);
  };

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (audioEl) {
        audioEl.pause();
        audioEl.src = '';
      }
    };
  }, [audioEl]);

  const renderItem = ({ item }: { item: BlippItem }) => {
    const id = item.blipp_id || item.id;
    const isPlayingInline = activeInlineId === id;
    const gradient = item.coverGradient || ['#1e1b4b', '#312e81'];

    return (
      <Pressable
        style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
        onPress={() => {
          if (audioEl) {
            audioEl.pause();
            setActiveInlineId(null);
          }
          setActiveReelItem(item);
        }}
        accessibilityRole="button"
        accessibilityLabel={`Saved blipp: ${item.title}`}
        testID={`saved-item-${id}`}
      >
        {/* Decorative Acoustic Accent Bar */}
        <View style={[styles.cardAccent, { backgroundColor: gradient[0] }]} />

        {/* Card Content Area */}
        <View style={styles.cardBody}>
          <View style={styles.cardHeaderRow}>
            <View style={styles.creatorBadge}>
              <View style={[styles.avatarCircle, { backgroundColor: gradient[1] }]}>
                <Text style={styles.avatarInitial}>
                  {(item.author || 'C').charAt(0).toUpperCase()}
                </Text>
              </View>
              <Text style={styles.creatorName} numberOfLines={1}>
                {item.author || 'Creator'}
              </Text>
            </View>

            {/* Unsave Bookmark Button */}
            <Pressable
              style={({ pressed }) => [
                styles.unsaveBtn,
                pressed && styles.btnPressed,
              ]}
              onPress={() => handleUnsave(id)}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              accessibilityRole="button"
              accessibilityLabel="Remove from saved"
              testID={`unsave-button-${id}`}
            >
              <BookmarkMark size={18} color={PALETTE.accent} filled={true} />
            </Pressable>
          </View>

          {/* Title */}
          <Text style={styles.cardTitle} numberOfLines={2}>
            {item.title}
          </Text>

          {/* Bottom Telemetry & Quick Play Row */}
          <View style={styles.cardFooter}>
            <View style={styles.metaRow}>
              <View style={styles.durationPill}>
                <Text style={styles.durationText}>
                  {formatDuration(item.duration_seconds || item.duration || 0)}
                </Text>
              </View>
              <Text style={styles.tapToPlayHint}>Tap to view full reel</Text>
            </View>

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
              accessibilityLabel={isPlayingInline ? 'Pause audio' : 'Play audio preview'}
              testID={`inline-play-${id}`}
            >
              {isPlayingInline ? (
                <PauseMark size={16} color="#ffffff" />
              ) : (
                <PlayMark size={16} color="#ffffff" />
              )}
            </Pressable>
          </View>
        </View>
      </Pressable>
    );
  };

  return (
    <View style={styles.root}>
      {/* Studio Header Bar */}
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <View style={styles.headerTitleRow}>
          <Text style={styles.headerTitle}>Saved</Text>
          {items.length > 0 && (
            <View style={styles.countBadge}>
              <Text style={styles.countBadgeText}>{items.length}</Text>
            </View>
          )}
        </View>
        <Text style={styles.headerSubtitle}>
          Archived audio broadcasts & saved moments
        </Text>
      </View>

      {/* List / Empty State */}
      <FlatList
        data={items}
        keyExtractor={(item) => item.blipp_id || item.id}
        renderItem={renderItem}
        contentContainerStyle={[
          styles.listContent,
          items.length === 0 && styles.listContentEmpty,
        ]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={onRefresh}
            tintColor={PALETTE.accent}
            colors={[PALETTE.accent]}
          />
        }
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyWrap} testID="saved-empty-state">
              <View style={styles.emptyIconCircle}>
                <BookmarkMark size={36} color={PALETTE.textMuted} filled={false} />
              </View>
              <Text style={styles.emptyHeading}>No saved Blipps yet</Text>
              <Text style={styles.emptySubtext}>
                Tap the bookmark icon on any broadcast to archive it in your studio library.
              </Text>
            </View>
          ) : null
        }
      />

      {/* Full Screen Audio Reel Modal */}
      {activeReelItem && (
        <Modal
          visible={Boolean(activeReelItem)}
          animationType="slide"
          presentationStyle="fullScreen"
          onRequestClose={() => setActiveReelItem(null)}
        >
          <View style={styles.modalRoot}>
            <View style={[styles.modalHeader, { paddingTop: insets.top + 10 }]}>
              <Pressable
                style={({ pressed }) => [
                  styles.modalCloseBtn,
                  pressed && styles.btnPressed,
                ]}
                onPress={() => setActiveReelItem(null)}
                accessibilityRole="button"
                accessibilityLabel="Close player"
                testID="close-reel-modal-button"
              >
                <Text style={styles.modalCloseText}>✕ Done</Text>
              </Pressable>
            </View>

            <View style={styles.modalReelContainer}>
              <AudioReel
                item={activeReelItem}
                isActive={true}
                height={600}
                onLike={() => {}}
                feedItems={[activeReelItem]}
                activeIndex={0}
              />
            </View>
          </View>
        </Modal>
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
    paddingHorizontal: 20,
    paddingBottom: 14,
    backgroundColor: PALETTE.surface,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 24,
    color: PALETTE.text,
    letterSpacing: -0.5,
  },
  countBadge: {
    backgroundColor: PALETTE.accentDim,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: PALETTE.accent,
  },
  countBadgeText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: PALETTE.accent,
  },
  headerSubtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    marginTop: 2,
  },
  listContent: {
    padding: 16,
    gap: 12,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
  },
  listContentEmpty: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  card: {
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  cardPressed: {
    backgroundColor: PALETTE.cardHover,
    borderColor: PALETTE.accent,
  },
  cardAccent: {
    width: 6,
  },
  cardBody: {
    flex: 1,
    padding: 14,
    gap: 8,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  creatorBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  avatarCircle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 12,
    color: '#ffffff',
  },
  creatorName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.textSecondary,
    flex: 1,
  },
  unsaveBtn: {
    padding: 4,
    borderRadius: 6,
  },
  cardTitle: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 16,
    color: PALETTE.text,
    lineHeight: 22,
  },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 4,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  durationPill: {
    backgroundColor: PALETTE.surface,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  durationText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textMuted,
    fontVariant: ['tabular-nums'],
  },
  tapToPlayHint: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  inlinePlayBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  inlinePlayBtnActive: {
    backgroundColor: '#dc2626',
  },
  btnPressed: {
    opacity: 0.7,
  },
  // Empty State
  emptyWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
    gap: 12,
  },
  emptyIconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 4,
  },
  emptyHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
    textAlign: 'center',
  },
  emptySubtext: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 280,
  },
  // Modal Full Reel
  modalRoot: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingHorizontal: 20,
    paddingBottom: 10,
    backgroundColor: PALETTE.bg,
    zIndex: 20,
  },
  modalCloseBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: PALETTE.surface,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  modalCloseText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.text,
  },
  modalReelContainer: {
    flex: 1,
    justifyContent: 'center',
  },
});
