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
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { PALETTE } from '@/lib/palette';
import { PlayMark, PauseMark, HeartMark, BookmarkMark } from '@/components/common/Icons';
import { useAudioPlayer } from '@/lib/audio/useAudioPlayer';
import { useEngagementTelemetry } from '@/lib/audio/useEngagementTelemetry';
import { useAudioPrefetch } from '@/lib/audio/useAudioPrefetch';
import { api } from '@/lib/api';
import type { AudioPost, Blipp } from '@/lib/types';

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

  // ── Engagement States (Save / Follow) ───────────────────────────────────────
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

  // ── §6.4 Speculative prefetch ──────────────────────────────────────────────
  // Pre-download the next 2–3 upcoming audio tracks so playback starts instantly.
  const { getCachedUri } = useAudioPrefetch({
    items: feedItems,
    activeIndex,
    enabled: isActive,
  });
  const localUri = blippId ? getCachedUri(blippId) : null;

  // ── Audio player ───────────────────────────────────────────────────────────
  // Manages Web Audio lifecycle, active position, playback controls.
  const {
    isPlaying,
    positionSeconds,
    durationSeconds,
    progress,
    togglePlayPause,
  } = useAudioPlayer({ item, isActive, localUri });

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
});
