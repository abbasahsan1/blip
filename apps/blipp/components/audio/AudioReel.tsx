/**
 * AudioReel
 *
 * Vertically-scrollable audio card for the Blipp feed. Responsible strictly for:
 *   - Vertical swipe / scroll gesture surface (managed by parent FlatList)
 *   - Play/Pause tap toggle (delegated to useAudioPlayer)
 *   - Animated waveform visualization (reacts to isPlaying)
 *   - Progress track (driven by progress from useAudioPlayer)
 *   - Metadata rendering: title, creator, tags, sponsored CTA
 *   - Like interaction (delegated via onLike prop)
 *
 * All Audio.Sound imperative calls, setInterval telemetry timers, and direct
 * telemetry dispatches have been extracted into:
 *   - useAudioPlayer      — audio lifecycle, play/pause, skip/complete events
 *   - useEngagementTelemetry — periodic 5-second play_progress telemetry
 *   - useAudioPrefetch    — §6.4 speculative prefetch of upcoming audio
 */

import { useState, useEffect, useRef } from 'react';
import {
  Animated,
  FlatList,
  Linking,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { PALETTE } from '@/lib/palette';
import {
  PlayMark,
  PauseMark,
  HeartMark,
  BookmarkMark,
  ShareMark,
} from '@/components/common/Icons';
import { useAudioPlayer } from '@/lib/audio/useAudioPlayer';
import { useEngagementTelemetry } from '@/lib/audio/useEngagementTelemetry';
import { useAudioPrefetch } from '@/lib/audio/useAudioPrefetch';
import { api } from '@/lib/api';
import type { AudioPost, Blipp, DMThreadItem } from '@/lib/types';

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatListens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  post?: AudioPost;
  item?: Blipp;
  isActive: boolean;
  height: number;
  onLike: () => void;
  onAutoSkip?: () => void;
  /**
   * Full feed item array — passed to useAudioPrefetch so it can speculatively
   * download upcoming audio before the user swipes to it (§6.4).
   * Gracefully degrades (no prefetching) if omitted.
   */
  feedItems?: Blipp[];
  /**
   * Index of this card within feedItems — used to determine which items to
   * prefetch ahead. Omit if feedItems is not provided.
   */
  activeIndex?: number;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AudioReel({
  post,
  item: propItem,
  isActive,
  height,
  onLike,
  onAutoSkip,
  feedItems = [],
  activeIndex = 0,
}: Props) {
  const item = (post || propItem) as Blipp;
  const isAd = Boolean(item?.is_ad || item?.is_sponsored);
  const blippId = item?.blipp_id || item?.id;
  const creatorId = item?.creator?.id || item?.creator_id || item?.authorId;
  const creatorDisplayName =
    item?.creator?.display_name ||
    item?.creator?.username ||
    item?.author ||
    'Creator';

  // ── Engagement States (Save / Follow / Share) ────────────────────────────────
  const [isSaved, setIsSaved] = useState(Boolean(item?.is_saved));
  const [isSaveLoading, setIsSaveLoading] = useState(false);

  useEffect(() => {
    setIsSaved(Boolean(item?.is_saved));
  }, [item?.is_saved]);

  const handleSaveToggle = async () => {
    if (!blippId || isSaveLoading) return;
    setIsSaveLoading(true);
    const nextState = !isSaved;
    setIsSaved(nextState);
    try {
      if (nextState) {
        await api.saveBlipp(blippId);
      } else {
        await api.unsaveBlipp(blippId);
      }
    } catch {
      setIsSaved(!nextState);
    } finally {
      setIsSaveLoading(false);
    }
  };

  const [isFollowing, setIsFollowing] = useState(Boolean(item?.is_following));
  const [isFollowLoading, setIsFollowLoading] = useState(false);

  useEffect(() => {
    setIsFollowing(Boolean(item?.is_following));
  }, [item?.is_following]);

  const handleFollowToggle = async () => {
    if (!creatorId || isFollowLoading) return;
    setIsFollowLoading(true);
    const nextState = !isFollowing;
    setIsFollowing(nextState);
    try {
      if (nextState) {
        await api.followUser(creatorId);
      } else {
        await api.unfollowUser(creatorId);
      }
    } catch {
      setIsFollowing(!nextState);
    } finally {
      setIsFollowLoading(false);
    }
  };

  // Direct Messaging Share Sheet
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [shareThreads, setShareThreads] = useState<DMThreadItem[]>([]);
  const [isSharing, setIsSharing] = useState(false);
  const [shareFeedback, setShareFeedback] = useState<string | null>(null);

  const openShareSheet = async () => {
    setIsShareModalOpen(true);
    setShareFeedback(null);
    try {
      const data = await api.getThreads(20, 0);
      setShareThreads(data || []);
    } catch {
      setShareThreads([]);
    }
  };

  const handleShareToThread = async (threadId: string, name: string) => {
    if (!blippId || isSharing) return;
    setIsSharing(true);
    try {
      await api.sendMessage(threadId, {
        message_type: 'blipp_share',
        blipp_id: blippId,
        body: item?.title || 'Shared Blipp broadcast',
      });
      setShareFeedback(`Shared with ${name}!`);
      setTimeout(() => {
        setIsShareModalOpen(false);
        setShareFeedback(null);
      }, 900);
    } catch {
      setShareFeedback('Failed to share.');
    } finally {
      setIsSharing(false);
    }
  };

  // ── §6.4 Speculative prefetch ──────────────────────────────────────────────
  // Pre-download the next 2–3 upcoming audio tracks so playback starts instantly.
  const { getCachedUri } = useAudioPrefetch({
    items: feedItems,
    activeIndex,
    enabled: isActive,
  });
  const localUri = blippId ? getCachedUri(blippId) : null;

  // ── Audio player ───────────────────────────────────────────────────────────
  // Manages Web Audio lifecycle, active position, playback controls & ad resilience.
  const {
    isPlaying,
    positionSeconds,
    durationSeconds,
    progress,
    togglePlayPause,
    isAdFallback,
    adCountdown,
  } = useAudioPlayer({ item, isActive, localUri });

  // Auto-skip sponsored slot on countdown expiration
  useEffect(() => {
    if (isAdFallback && isActive && adCountdown <= 0) {
      onAutoSkip?.();
    }
  }, [isAdFallback, isActive, adCountdown, onAutoSkip]);

  // ── Engagement telemetry ───────────────────────────────────────────────────
  // Emits periodic 5s play_progress, terminal play_complete (>=90%), and skip on navigate.
  const { dispatchLike } = useEngagementTelemetry({
    item,
    isPlaying,
    positionSeconds,
    durationSeconds,
    isActive,
  });

  const handleLike = async () => {
    onLike();
    await dispatchLike();
  };

  // ── Animated waveform ──────────────────────────────────────────────────────
  // 36 bars animated in a staggered loop while isPlaying; decay to rest when paused.
  const bars = useRef(
    Array.from({ length: 36 }, () => new Animated.Value(0.2)),
  ).current;
  const playAnim = useRef<Animated.CompositeAnimation | null>(null);

  useEffect(() => {
    if (isPlaying) {
      const anims = bars.map((bar, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(i * 35),
            Animated.timing(bar, {
              toValue: 0.25 + Math.random() * 0.75,
              duration: 250 + Math.random() * 250,
              useNativeDriver: false,
            }),
            Animated.timing(bar, {
              toValue: 0.12 + Math.random() * 0.25,
              duration: 250 + Math.random() * 200,
              useNativeDriver: false,
            }),
          ]),
        ),
      );
      playAnim.current = Animated.parallel(anims);
      playAnim.current.start();
    } else {
      playAnim.current?.stop();
      bars.forEach((b) =>
        Animated.timing(b, {
          toValue: 0.2,
          duration: 180,
          useNativeDriver: false,
        }).start(),
      );
    }

    return () => {
      playAnim.current?.stop();
    };
  }, [isPlaying, bars]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const displayDuration = durationSeconds || item?.duration || 0;

  return (
    <View style={[styles.root, { height }]} testID="audio-reel-card">
      {/* Studio console backdrop: solid, deadened acoustics */}
      <View style={styles.consoleBackdrop} />

      {/* Main sound deck content */}
      <View style={styles.content}>
        {/* Header telemetry row: Source chip & Sponsored indicator */}
        <View style={styles.headerRow}>
          {item?.sourceName && (
            <View style={styles.sourceChip}>
              <Text style={styles.sourceText} numberOfLines={1}>
                {item.sourceName}
              </Text>
            </View>
          )}

          {isAd && (
            <View style={styles.sponsoredBadge} testID="sponsored-pill-badge">
              <Text style={styles.sponsoredBadgeText}>Sponsored</Text>
            </View>
          )}
        </View>

        {/* Blipp Title: Sora Display Typography */}
        <Text style={styles.title} numberOfLines={3} testID="blipp-title">
          {item?.title}
        </Text>

        {/* Creator Attribution */}
        <View style={styles.authorRow}>
          <Text style={styles.author}>{creatorDisplayName}</Text>
          {item?.sponsor?.tagline && (
            <Text style={styles.sponsorTagline} numberOfLines={1}>
              · {item.sponsor.tagline}
            </Text>
          )}
          {!isAd && creatorId && (
            <Pressable
              style={({ pressed }) => [
                styles.followBtn,
                isFollowing && styles.followingBtn,
                pressed && styles.actionBtnPressed,
              ]}
              onPress={handleFollowToggle}
              disabled={isFollowLoading}
              accessibilityRole="button"
              accessibilityLabel={isFollowing ? 'Unfollow creator' : 'Follow creator'}
              testID="follow-creator-button"
            >
              <Text
                style={[
                  styles.followBtnText,
                  isFollowing && styles.followingBtnText,
                ]}
              >
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            </Pressable>
          )}
        </View>

        {/* Waveform Frequency Meters */}
        <View style={styles.waveformContainer}>
          <View style={styles.waveform}>
            {bars.map((bar, i) => {
              const barFraction = i / bars.length;
              const hasPassed = barFraction <= progress;
              return (
                <Animated.View
                  key={i}
                  style={[
                    styles.waveBar,
                    {
                      height: bar.interpolate({
                        inputRange: [0, 1],
                        outputRange: ['8%', '100%'],
                      }),
                      backgroundColor: hasPassed ? PALETTE.accent : '#27272a',
                      opacity: isPlaying ? 1 : 0.45,
                    },
                  ]}
                />
              );
            })}
          </View>

          {/* Timecode Needle Track */}
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
          </View>
        </View>

        {/* Tactile Controls Cluster */}
        <View style={styles.controls} testID="audio-player-container">
          <Pressable
            style={({ pressed }) => [
              styles.playBtn,
              pressed && styles.playBtnPressed,
            ]}
            onPress={togglePlayPause}
            accessibilityRole="button"
            accessibilityLabel={isPlaying ? 'Pause audio' : 'Play audio'}
            testID="audio-play-button"
          >
            {isPlaying ? (
              <PauseMark size={20} color="#ffffff" />
            ) : (
              <PlayMark size={20} color="#ffffff" />
            )}
          </Pressable>

          <View style={styles.meta}>
            <Text style={styles.timecodeActive}>
              {formatDuration(positionSeconds)}
            </Text>
            <Text style={styles.metaDivider}>/</Text>
            <Text style={styles.timecodeTotal}>
              {formatDuration(displayDuration)}
            </Text>
            <Text style={styles.metaDot}>•</Text>
            <Text style={styles.metaPlays}>
              {formatListens(item?.listenCount || 0)} plays
            </Text>
          </View>

          {/* Share / DM Button */}
          <Pressable
            style={({ pressed }) => [
              styles.actionBtn,
              pressed && styles.actionBtnPressed,
            ]}
            onPress={openShareSheet}
            accessibilityRole="button"
            accessibilityLabel="Share blipp to direct message"
            testID="share-blipp-button"
          >
            <ShareMark size={20} color={PALETTE.textSecondary} />
            <Text style={styles.actionBtnText}>Share</Text>
          </Pressable>

          {/* Save / Bookmark Button */}
          <Pressable
            style={({ pressed }) => [
              styles.actionBtn,
              pressed && styles.actionBtnPressed,
            ]}
            onPress={handleSaveToggle}
            disabled={isSaveLoading}
            accessibilityRole="button"
            accessibilityLabel={isSaved ? 'Remove from saved' : 'Save blipp'}
            testID="save-blipp-button"
          >
            <BookmarkMark
              size={20}
              color={isSaved ? PALETTE.accent : PALETTE.textSecondary}
              filled={isSaved}
            />
            <Text
              style={[
                styles.actionBtnText,
                isSaved && styles.actionBtnTextActive,
              ]}
            >
              {isSaved ? 'Saved' : 'Save'}
            </Text>
          </Pressable>

          {/* Like Button */}
          <Pressable
            style={({ pressed }) => [
              styles.actionBtn,
              pressed && styles.actionBtnPressed,
            ]}
            onPress={handleLike}
            accessibilityRole="button"
            accessibilityLabel={item?.isLiked ? 'Unlike audio' : 'Like audio'}
            testID="like-blipp-button"
          >
            <HeartMark
              size={20}
              color={item?.isLiked ? PALETTE.accent : PALETTE.textSecondary}
              filled={item?.isLiked}
            />
            <Text
              style={[
                styles.actionBtnText,
                item?.isLiked && styles.actionBtnTextActive,
              ]}
            >
              {formatListens(item?.likeCount || 0)}
            </Text>
          </Pressable>
        </View>

        {/* Sponsored Promo Fallback Card (Visual Ad with 5s countdown when audio is unavailable) */}
        {isAd && isAdFallback && (
          <View style={styles.adPromoCard} testID="sponsored-promo-fallback-card">
            <View style={styles.adPromoHeader}>
              <View style={styles.adBadge}>
                <Text style={styles.adBadgeText}>SPONSORED PROMOTION</Text>
              </View>
              <Pressable
                style={styles.skipNowBtn}
                onPress={() => onAutoSkip?.()}
                accessibilityRole="button"
                accessibilityLabel="Skip sponsored ad"
                testID="skip-ad-button"
              >
                <Text style={styles.skipNowText}>Skip ({adCountdown}s)</Text>
              </Pressable>
            </View>
            <Text style={styles.adPromoTagline}>
              {item?.sponsor?.tagline || 'Experience partner highlights curated for your stream.'}
            </Text>
            {/* Auto-skip countdown progress bar */}
            <View style={styles.adCountdownTrack}>
              <View
                style={[
                  styles.adCountdownFill,
                  { width: `${((5 - adCountdown) / 5) * 100}%` },
                ]}
              />
            </View>
          </View>
        )}

        {/* Sponsored Call To Action: Clean text trigger, no decorative arrows */}
        {item?.is_sponsored && item?.sponsor && (
          <Pressable
            style={({ pressed }) => [
              styles.ctaButton,
              pressed && styles.ctaButtonPressed,
            ]}
            onPress={() =>
              item.sponsor?.cta_url && Linking.openURL(item.sponsor.cta_url)
            }
            accessibilityRole="button"
            accessibilityLabel={item.sponsor.cta_text || 'Learn more'}
          >
            <Text style={styles.ctaText}>
              {item.sponsor.cta_text || 'Learn More'}
            </Text>
          </Pressable>
        )}

        {/* Content Tags */}
        {item?.tags && item.tags.length > 0 && !item.is_sponsored && (
          <View style={styles.tags}>
            {item.tags.map((tag) => (
              <View key={tag} style={styles.tag}>
                <Text style={styles.tagText}>#{tag}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Share / Direct Message Modal */}
      <Modal
        visible={isShareModalOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setIsShareModalOpen(false)}
      >
        <Pressable
          style={styles.shareOverlay}
          onPress={() => setIsShareModalOpen(false)}
        >
          <Pressable style={styles.shareSheet} onPress={(e) => e.stopPropagation()}>
            <View style={styles.shareHandle} />
            <Text style={styles.shareTitle}>Share Blipp to Direct Message</Text>
            {shareFeedback && (
              <Text style={styles.shareFeedbackText}>{shareFeedback}</Text>
            )}
            <FlatList
              data={shareThreads}
              keyExtractor={(t) => t.thread_id}
              style={styles.shareList}
              ListEmptyComponent={
                <View style={styles.emptyThreads}>
                  <Text style={styles.emptyThreadsText}>No recent DM conversations found</Text>
                </View>
              }
              renderItem={({ item: thread }) => (
                <Pressable
                  style={({ pressed }) => [
                    styles.threadShareRow,
                    pressed && styles.threadShareRowPressed,
                  ]}
                  onPress={() =>
                    handleShareToThread(
                      thread.thread_id,
                      thread.other_participant?.display_name ||
                        thread.other_participant?.username ||
                        'user'
                    )
                  }
                  disabled={isSharing}
                >
                  <View style={styles.threadAvatar}>
                    <Text style={styles.threadAvatarText}>
                      {(
                        thread.other_participant?.display_name ||
                        thread.other_participant?.username ||
                        'U'
                      )[0].toUpperCase()}
                    </Text>
                  </View>
                  <View style={styles.threadInfo}>
                    <Text style={styles.threadName}>
                      {thread.other_participant?.display_name ||
                        thread.other_participant?.username ||
                        'Conversation'}
                    </Text>
                    <Text style={styles.threadUsername}>
                      @{thread.other_participant?.username || 'user'}
                    </Text>
                  </View>
                  <View style={styles.sendChip}>
                    <Text style={styles.sendChipText}>Send</Text>
                  </View>
                </Pressable>
              )}
            />
            <Pressable
              style={styles.closeShareBtn}
              onPress={() => setIsShareModalOpen(false)}
            >
              <Text style={styles.closeShareText}>Cancel</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: {
    width: '100%',
    backgroundColor: PALETTE.bg,
    overflow: 'hidden',
    position: 'relative',
  },
  consoleBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: PALETTE.bg,
  },
  content: {
    flex: 1,
    justifyContent: 'flex-end',
    paddingHorizontal: 24,
    paddingBottom: 84,
    paddingTop: 80,
    gap: 14,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  sourceChip: {
    alignSelf: 'flex-start',
    backgroundColor: PALETTE.card,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  sourceText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: PALETTE.textSecondary,
    letterSpacing: 0.2,
  },
  sponsoredBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.12)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.3)',
  },
  sponsoredBadgeText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 11,
    color: '#fbbf24',
  },
  title: {
    fontFamily: 'Sora_700Bold',
    fontSize: 24,
    color: PALETTE.text,
    lineHeight: 32,
    letterSpacing: -0.5,
  },
  authorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  author: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  followBtn: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 14,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 6,
    minHeight: 28,
  },
  followingBtn: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  followBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: '#ffffff',
  },
  followingBtnText: {
    color: PALETTE.textSecondary,
  },
  sponsorTagline: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    flex: 1,
  },
  waveformContainer: {
    gap: 6,
    marginVertical: 4,
  },
  waveform: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 48,
    gap: 3,
  },
  waveBar: {
    flex: 1,
    borderRadius: 2,
    minHeight: 4,
  },
  progressTrack: {
    height: 2,
    backgroundColor: PALETTE.border,
    borderRadius: 1,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: PALETTE.accent,
    borderRadius: 1,
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  playBtn: {
    width: 48,
    height: 48,
    borderRadius: 8,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  playBtnPressed: {
    backgroundColor: PALETTE.cardHover,
    borderColor: PALETTE.accent,
  },
  meta: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  timecodeActive: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.text,
    fontVariant: ['tabular-nums'],
  },
  metaDivider: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  timecodeTotal: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    fontVariant: ['tabular-nums'],
  },
  metaDot: {
    color: PALETTE.border,
    marginHorizontal: 2,
  },
  metaPlays: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: PALETTE.textMuted,
    fontVariant: ['tabular-nums'],
  },
  actionBtn: {
    alignItems: 'center',
    gap: 3,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 8,
    borderRadius: 6,
  },
  actionBtnPressed: {
    opacity: 0.7,
  },
  actionBtnText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textMuted,
    fontVariant: ['tabular-nums'],
  },
  actionBtnTextActive: {
    color: PALETTE.accent,
  },
  likeBtn: {
    alignItems: 'center',
    gap: 3,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 8,
    borderRadius: 6,
  },
  likeBtnPressed: {
    opacity: 0.7,
  },
  likeCount: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textMuted,
    fontVariant: ['tabular-nums'],
  },
  likeCountActive: {
    color: PALETTE.accent,
  },
  ctaButton: {
    backgroundColor: PALETTE.accent,
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  ctaButtonPressed: {
    opacity: 0.85,
  },
  ctaText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#ffffff',
  },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tag: {
    paddingHorizontal: 9,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.borderSubtle,
  },
  tagText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  // Sponsored Promo Fallback
  adPromoCard: {
    backgroundColor: '#18181b',
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.35)',
    borderRadius: 12,
    padding: 14,
    gap: 10,
    marginTop: 4,
  },
  adPromoHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  adBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  adBadgeText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 10,
    color: '#fbbf24',
    letterSpacing: 0.5,
  },
  skipNowBtn: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  skipNowText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 11,
    color: PALETTE.textSecondary,
  },
  adPromoTagline: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13,
    color: PALETTE.text,
    lineHeight: 18,
  },
  adCountdownTrack: {
    height: 3,
    backgroundColor: PALETTE.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  adCountdownFill: {
    height: '100%',
    backgroundColor: '#fbbf24',
    borderRadius: 2,
  },
  // DM Share Sheet
  shareOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
  },
  shareSheet: {
    backgroundColor: PALETTE.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 12,
    paddingBottom: 36,
    paddingHorizontal: 20,
    maxHeight: '65%',
    borderTopWidth: 1,
    borderColor: PALETTE.border,
  },
  shareHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.border,
    alignSelf: 'center',
    marginBottom: 16,
  },
  shareTitle: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 18,
    color: PALETTE.text,
    marginBottom: 12,
  },
  shareFeedbackText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.accent,
    marginBottom: 10,
  },
  shareList: {
    maxHeight: 280,
  },
  emptyThreads: {
    paddingVertical: 24,
    alignItems: 'center',
  },
  emptyThreadsText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
  },
  threadShareRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.borderSubtle,
    gap: 12,
  },
  threadShareRowPressed: {
    opacity: 0.7,
  },
  threadAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  threadAvatarText: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 15,
    color: PALETTE.accent,
  },
  threadInfo: {
    flex: 1,
  },
  threadName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  threadUsername: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  sendChip: {
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 14,
  },
  sendChipText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: '#ffffff',
  },
  closeShareBtn: {
    marginTop: 16,
    paddingVertical: 12,
    backgroundColor: PALETTE.card,
    borderRadius: 8,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  closeShareText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
});
