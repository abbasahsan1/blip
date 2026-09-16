/**
 * AudioReel
 *
 * Full-bleed, edge-to-edge dark audio card for the Blipp feed.
 * Expressive social aesthetics:
 *   - Deep obsidian canvas with ambient radial glow responsive to playback
 *   - Center dynamic visualizer: 5 pulsing audio equalizer bars dancing while isPlaying
 *   - Floating Action Dock (Right Side): High-contrast floating pill stack for Like, Stash, Echo, and Report
 *   - Bottom Overlay: Bold creator handle, glowing Follow button, and an interactive waveform scrub-bar with live timestamps
 */

import { useState, useEffect, useRef } from 'react';
import {
  Animated,
  Dimensions,
  FlatList,
  Image,
  Linking,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { PALETTE } from '@/lib/palette';
import { Feather } from '@expo/vector-icons';
import { useAudioPlayer } from '@/lib/audio/useAudioPlayer';
import { useAudioPrefetch } from '@/lib/audio/useAudioPrefetch';
import { api, resolveMediaUrl } from '@/lib/api';
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
  onLike: () => Promise<void>;
  onAutoSkip?: () => void;
  feedItems?: Blipp[];
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
  const rawItem = (post || propItem) as Blipp;
  const item: Blipp = rawItem
    ? {
        ...rawItem,
        audio_url: resolveMediaUrl(rawItem.audio_url),
        audio_variants: {
          standard: resolveMediaUrl(rawItem.audio_variants?.standard || rawItem.audio_url),
          low: resolveMediaUrl(rawItem.audio_variants?.low || rawItem.audio_variants?.standard || rawItem.audio_url),
          high: resolveMediaUrl(rawItem.audio_variants?.high || rawItem.audio_variants?.standard || rawItem.audio_url),
        },
      }
    : rawItem;
  const isAd = Boolean(item?.is_ad || item?.is_sponsored);
  const blippId = item?.blipp_id || item?.id;
  const creatorId = item?.creator?.id || item?.creator_id || item?.authorId;
  const creatorDisplayName =
    item?.creator?.display_name ||
    item?.creator?.username ||
    item?.author ||
    'Creator';
  const creatorHandle =
    item?.creator?.username ||
    (item as any)?.author ||
    (item as any)?.username ||
    'creator';

  // ── Engagement States (Save / Follow / Share / Report) ───────────────────────
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
      setShareFeedback(`Echoed to ${name}!`);
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

  // Moderation Report Modal
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [reportReason, setReportReason] = useState<string>('inappropriate');
  const [isSubmittingReport, setIsSubmittingReport] = useState(false);
  const [reportSubmitted, setReportSubmitted] = useState(false);

  const handleReportSubmit = async () => {
    if (!blippId || isSubmittingReport) return;
    setIsSubmittingReport(true);
    try {
      await api.post('/v1/reports', {
        blipp_id: blippId,
        reason: reportReason,
      });
      setReportSubmitted(true);
      setTimeout(() => {
        setIsReportModalOpen(false);
        setReportSubmitted(false);
      }, 1200);
    } catch {
      setReportSubmitted(true);
      setTimeout(() => {
        setIsReportModalOpen(false);
        setReportSubmitted(false);
      }, 1200);
    } finally {
      setIsSubmittingReport(false);
    }
  };

  // ── Speculative prefetch ───────────────────────────────────────────────────
  const { getCachedUri } = useAudioPrefetch({
    items: feedItems,
    activeIndex,
    enabled: isActive,
  });
  const localUri = blippId ? getCachedUri(blippId) : null;

  // ── Audio player ───────────────────────────────────────────────────────────
  const {
    isPlaying,
    positionSeconds,
    durationSeconds,
    progress,
    togglePlayPause,
    seekTo,
    isAdFallback,
    adCountdown,
  } = useAudioPlayer({ item, isActive, localUri });

  // Auto-skip sponsored slot on countdown expiration
  useEffect(() => {
    if (isAdFallback && isActive && adCountdown <= 0) {
      onAutoSkip?.();
    }
  }, [isAdFallback, isActive, adCountdown, onAutoSkip]);

  // Like bouncing heart animation
  const heartScale = useRef(new Animated.Value(1)).current;

  const handleLike = async () => {
    Animated.sequence([
      Animated.spring(heartScale, { toValue: 1.5, friction: 3, useNativeDriver: true }),
      Animated.spring(heartScale, { toValue: 1, friction: 4, useNativeDriver: true }),
    ]).start();
    await onLike();
  };

  // Animated scrolling audio track tag
  const trackTagAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let loop: Animated.CompositeAnimation | null = null;
    if (isPlaying) {
      loop = Animated.loop(
        Animated.sequence([
          Animated.timing(trackTagAnim, {
            toValue: -80,
            duration: 4500,
            useNativeDriver: true,
          }),
          Animated.timing(trackTagAnim, {
            toValue: 0,
            duration: 0,
            useNativeDriver: true,
          }),
        ]),
      );
      loop.start();
    } else {
      trackTagAnim.setValue(0);
    }
    return () => {
      loop?.stop();
    };
  }, [isPlaying, trackTagAnim]);

  // Scrub bar interaction
  const handleScrub = (event: any) => {
    const layoutWidth = event.nativeEvent.layout?.width || Dimensions.get('window').width;
    const clickX = event.nativeEvent.locationX;
    const ratio = Math.max(0, Math.min(1, clickX / layoutWidth));
    const targetSeconds = Math.floor(ratio * (durationSeconds || item?.duration || 0));
    seekTo(targetSeconds);
  };

  const displayDuration = durationSeconds || item?.duration || 0;

  const reelHeight = height || Dimensions.get('window').height;

  return (
    <View style={[styles.root, { height: reelHeight }]} testID="audio-reel-card">
      {/* 1. Edge-to-edge dark/orange canvas */}
      <LinearGradient
        colors={['#000000', '#090A0F', '#000000']}
        style={StyleSheet.absoluteFill}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 1 }}
      />

      {/* 2. Center Stage with tactile play/pause (Moved lower for one-handed use) */}
      <Pressable
        style={styles.centerStage}
        onPress={togglePlayPause}
        accessibilityRole="button"
        accessibilityLabel={isPlaying ? 'Pause broadcast' : 'Play broadcast'}
        testID="center-play-pause-trigger"
      >
        <View style={styles.centerVisualizerBox}>

          {/* Center tactile play / pause status badge */}
          <View style={[styles.centerPlayBadge, isPlaying && styles.centerPlayBadgePlaying]}>
            {isPlaying ? (
              <Feather name="pause" size={24} color="#FFFFFF" />
            ) : (
              <Feather name="play" size={26} color="#FFFFFF" />
            )}
          </View>
        </View>
      </Pressable>

      {/* 3. Floating Thumb-Friendly Action Column (Right Side) */}
      <View style={styles.floatingActionColumn} testID="floating-action-dock">
        <View style={styles.profileItem}>
          {item?.creator?.avatar_url || (item as any)?.avatar_url ? (
            <Image
              source={{ uri: item?.creator?.avatar_url || (item as any)?.avatar_url }}
              style={styles.profilePicture}
              accessibilityLabel={`${creatorDisplayName}'s profile picture`}
            />
          ) : (
            <View style={styles.profileFallback}>
              <Text style={styles.profileInitial}>{creatorDisplayName.slice(0, 1).toUpperCase()}</Text>
            </View>
          )}
        </View>
        {/* Like Button (Bouncing heart + count) */}
        <View style={styles.actionItemWrapper}>
          <Pressable
            style={({ pressed }) => [
              styles.actionFrostedBtn,
              pressed && styles.frostedBtnPressed,
            ]}
            onPress={handleLike}
            accessibilityRole="button"
            accessibilityLabel={item?.isLiked ? 'Unlike broadcast' : 'Like broadcast'}
            testID="like-blipp-button"
          >
            <Animated.View style={{ transform: [{ scale: heartScale }] }}>
              <Feather name="heart" size={24} color={item?.isLiked ? "#F97316" : "#FFFFFF"} />
            </Animated.View>
          </Pressable>
          <Text
            style={[
              styles.actionCounterText,
              item?.isLiked && { color: '#F97316' },
            ]}
          >
            {formatListens(item?.likeCount || 0)}
          </Text>
        </View>

        {/* Stash / Bookmark Button */}
        <View style={styles.actionItemWrapper}>
          <Pressable
            style={({ pressed }) => [
              styles.actionFrostedBtn,
              pressed && styles.frostedBtnPressed,
            ]}
            onPress={handleSaveToggle}
            disabled={isSaveLoading}
            accessibilityRole="button"
            accessibilityLabel={isSaved ? 'Remove from stash' : 'Stash blipp'}
            testID="save-blipp-button"
          >
            <Feather name="bookmark" size={23} color={isSaved ? "#F59E0B" : "#FFFFFF"} />
          </Pressable>
          <Text
            style={[
              styles.actionCounterText,
              isSaved && { color: '#F59E0B' },
            ]}
          >
            {isSaved ? 'Saved' : 'Save'}
          </Text>
        </View>

        {/* Echo / DM Share Button */}
        <View style={styles.actionItemWrapper}>
          <Pressable
            style={({ pressed }) => [
              styles.actionFrostedBtn,
              pressed && styles.frostedBtnPressed,
            ]}
            onPress={openShareSheet}
            accessibilityRole="button"
            accessibilityLabel="Echo to direct message"
            testID="share-blipp-button"
          >
            <Feather name="send" size={22} color="#FFFFFF" />
          </Pressable>
          <Text style={styles.actionCounterText}>Echo</Text>
        </View>

        {/* Options (3 dots) */}
        <View style={styles.actionItemWrapper}>
          <Pressable
            style={({ pressed }) => [
              styles.actionFrostedBtn,
              pressed && styles.frostedBtnPressed,
            ]}
            onPress={() => setIsReportModalOpen(true)}
            accessibilityRole="button"
            accessibilityLabel="Blipp options"
            testID="report-content-button"
          >
            <Feather name="more-horizontal" size={22} color="#FFFFFF" />
          </Pressable>
          <Text style={styles.actionCounterText}>More</Text>
        </View>
      </View>

      {/* 4. Bottom Metadata Dock: Left-aligned at bottom: 100, left: 16, right: 80 */}
      <View style={styles.bottomMetadataDock} pointerEvents="box-none">
        {/* Creator handle with verified tick + sleek pill Follow button */}
        <View style={styles.creatorHeaderRow}>
          <View style={styles.creatorHandleContainer}>
            <Text style={styles.creatorHandleText} numberOfLines={1}>
              @{creatorHandle}
            </Text>
            <Feather name="check-circle" size={16} color="#F97316" />
          </View>

          {!isAd && creatorId && (
            <Pressable
              style={({ pressed }) => [
                styles.sleekPillFollowBtn,
                isFollowing && styles.sleekPillFollowingBtn,
                pressed && styles.followBtnPressed,
              ]}
              onPress={handleFollowToggle}
              disabled={isFollowLoading}
              accessibilityRole="button"
              accessibilityLabel={isFollowing ? 'Unfollow creator' : 'Follow creator'}
              testID="follow-creator-button"
            >
              <Text
                style={[
                  styles.sleekPillFollowText,
                  isFollowing && styles.sleekPillFollowingText,
                ]}
              >
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            </Pressable>
          )}
        </View>

        {/* Blipp Title */}
        <Text style={styles.blippTitle} numberOfLines={2} testID="blipp-title">
          {item?.title}
        </Text>

        {item?.description ? (
          <Text style={styles.blippDescription} numberOfLines={1}>
            {item.description}
          </Text>
        ) : null}

        {/* Sponsored Slot Indicator */}
        {isAd && (
          <View style={styles.sponsoredPillContainer}>
            <View style={styles.sponsoredPill}>
              <Text style={styles.sponsoredPillText}>SPONSORED</Text>
            </View>
            {item?.sponsor?.cta_url && (
              <Pressable
                style={styles.sponsoredCtaBtn}
                onPress={() => item.sponsor?.cta_url && Linking.openURL(item.sponsor.cta_url)}
              >
                <Text style={styles.sponsoredCtaText}>
                  {item.sponsor.cta_text || 'Learn More'}
                </Text>
              </Pressable>
            )}
          </View>
        )}

        {/* Animated scrolling audio track tag */}
        <View style={styles.audioTrackTagRow}>
          <Animated.View
            style={[
              styles.audioTrackTagInner,
              { transform: [{ translateX: trackTagAnim }] },
            ]}
          >
            <Text style={styles.audioTrackTagText} numberOfLines={1}>
              🎵 Original Sound - @{creatorHandle}
            </Text>
          </Animated.View>
        </View>
      </View>

      {/* 5. Thin, unobtrusive scrubber bar pinned along the very bottom */}
      <Pressable
        style={styles.bottomScrubberContainer}
        onPress={handleScrub}
        testID="bottom-scrubber-bar"
      >
        <View style={styles.bottomScrubberTrack}>
          <View
            style={[
              styles.bottomScrubberFill,
              { width: `${Math.max(0, Math.min(100, progress * 100))}%` },
            ]}
          />
        </View>
      </Pressable>

      {/* Share / Direct Message Modal */}
      <Modal
        visible={isShareModalOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setIsShareModalOpen(false)}
      >
        <Pressable
          style={styles.sheetOverlay}
          onPress={() => setIsShareModalOpen(false)}
        >
          <Pressable style={styles.sheetContainer} onPress={(e) => e.stopPropagation()}>
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Echo Blipp to Conversation</Text>
            {shareFeedback && (
              <Text style={styles.sheetFeedbackText}>{shareFeedback}</Text>
            )}
            <FlatList
              data={shareThreads}
              keyExtractor={(t) => t.thread_id}
              style={styles.sheetList}
              ListEmptyComponent={
                <View style={styles.emptyList}>
                  <Text style={styles.emptyListText}>No recent DM vibes found</Text>
                </View>
              }
              renderItem={({ item: thread }) => (
                <Pressable
                  style={({ pressed }) => [
                    styles.threadRow,
                    pressed && styles.threadRowPressed,
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
                  <View style={styles.echoChip}>
                    <Text style={styles.echoChipText}>Send</Text>
                  </View>
                </Pressable>
              )}
            />
          </Pressable>
        </Pressable>
      </Modal>

      {/* Moderation Report Modal */}
      <Modal
        visible={isReportModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setIsReportModalOpen(false)}
      >
        <Pressable
          style={styles.sheetOverlay}
          onPress={() => setIsReportModalOpen(false)}
        >
          <Pressable style={styles.reportModalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.reportHeading}>Report Broadcast</Text>
            <Text style={styles.reportSubheading}>
              Help keep the Blipp community safe. Why are you reporting this clip?
            </Text>

            {reportSubmitted ? (
              <View style={styles.reportSuccessBox}>
                <Feather name="check-circle" size={32} color={PALETTE.lime} />
                <Text style={styles.reportSuccessText}>Thank you for your report.</Text>
                <Text style={styles.reportSuccessSubtext}>Our moderation engine will review it promptly.</Text>
              </View>
            ) : (
              <>
                {[
                  { id: 'inappropriate', label: 'Inappropriate or Explicit Content' },
                  { id: 'harassment', label: 'Harassment or Hate Speech' },
                  { id: 'spam', label: 'Spam, Scam, or Misleading' },
                  { id: 'copyright', label: 'Copyright / IP Infringement' },
                ].map((reason) => (
                  <Pressable
                    key={reason.id}
                    style={[
                      styles.reasonRow,
                      reportReason === reason.id && styles.reasonRowActive,
                    ]}
                    onPress={() => setReportReason(reason.id)}
                  >
                    <View
                      style={[
                        styles.radioCircle,
                        reportReason === reason.id && styles.radioCircleActive,
                      ]}
                    />
                    <Text style={styles.reasonText}>{reason.label}</Text>
                  </Pressable>
                ))}

                <View style={styles.reportActionRow}>
                  <Pressable
                    style={styles.cancelBtn}
                    onPress={() => setIsReportModalOpen(false)}
                  >
                    <Text style={styles.cancelBtnText}>Cancel</Text>
                  </Pressable>

                  <Pressable
                    style={[styles.submitReportBtn, isSubmittingReport && { opacity: 0.6 }]}
                    onPress={handleReportSubmit}
                    disabled={isSubmittingReport}
                  >
                    <Text style={styles.submitReportText}>Submit Report</Text>
                  </Pressable>
                </View>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: {
    flex: 1,
    width: '100%',
    position: 'relative',
    backgroundColor: '#000000',
    overflow: 'hidden',
  },
  canvasBackground: {
    ...StyleSheet.absoluteFill,
    backgroundColor: '#000000',
  },
  ambientRadialGlow: {
    position: 'absolute',
    top: '30%',
    left: '20%',
    width: 240,
    height: 240,
    borderRadius: 120,
    backgroundColor: 'rgba(249, 115, 22, 0.18)',
    shadowColor: '#F97316',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 80,
  },
  centerStage: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'flex-end',
    paddingBottom: '40%', // Moves it to lower portion of screen
    alignItems: 'center',
    zIndex: 2,
  },
  centerVisualizerBox: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 170,
    height: 170,
  },
  eqCluster: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 72,
    gap: 8,
    marginBottom: 16,
  },
  eqBar: {
    width: 6,
    borderRadius: 3,
  },
  centerPlayBadge: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(17, 19, 27, 0.75)',
    borderWidth: 1.5,
    borderColor: 'rgba(255, 255, 255, 0.2)',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.5,
    shadowRadius: 12,
  },
  centerPlayBadgePlaying: {
    borderColor: '#F97316',
    backgroundColor: 'rgba(234, 88, 12, 0.3)',
  },

  // Floating Thumb-Friendly Action Column (Right Side)
  floatingActionColumn: {
    position: 'absolute',
    right: 16,
    bottom: 100,
    alignItems: 'center',
    gap: 16,
    zIndex: 10,
  },
  actionItemWrapper: {
    alignItems: 'center',
    gap: 4,
  },
  profileItem: {
    marginBottom: 2,
  },
  profilePicture: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 2,
    borderColor: '#F97316',
  },
  profileFallback: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#090A0F',
    borderWidth: 2,
    borderColor: '#F97316',
  },
  profileInitial: {
    color: '#FFFFFF',
    fontFamily: 'Outfit_700Bold',
    fontSize: 18,
  },
  actionFrostedBtn: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
  },
  frostedBtnPressed: {
    transform: [{ scale: 0.92 }],
    backgroundColor: 'rgba(255, 255, 255, 0.22)',
  },
  actionCounterText: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 11,
    color: '#FFFFFF',
    textShadowColor: 'rgba(0, 0, 0, 0.75)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },

  bottomMetadataDock: {
    position: 'absolute',
    bottom: 20,
    left: 16,
    right: 80,
    zIndex: 10,
    gap: 8,
  },
  creatorHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  creatorHandleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  creatorHandleText: {
    fontFamily: 'Outfit_700Bold',
    fontSize: 18,
    color: '#FFFFFF',
    letterSpacing: 0.2,
    textShadowColor: 'rgba(0, 0, 0, 0.65)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  sleekPillFollowBtn: {
    backgroundColor: 'rgba(249, 115, 22, 0.20)',
    borderWidth: 1,
    borderColor: '#F97316',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  sleekPillFollowingBtn: {
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  followBtnPressed: {
    transform: [{ scale: 0.95 }],
  },
  sleekPillFollowText: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 11,
    color: '#F97316',
  },
  sleekPillFollowingText: {
    color: 'rgba(255, 255, 255, 0.75)',
  },
  blippTitle: {
    fontFamily: 'Outfit_700Bold',
    fontSize: 20,
    color: '#FFFFFF',
    lineHeight: 20,
    textShadowColor: 'rgba(0, 0, 0, 0.75)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  blippDescription: {
    fontFamily: 'Outfit_400Regular',
    fontSize: 13,
    color: 'rgba(255, 255, 255, 0.75)',
    lineHeight: 17,
  },
  sponsoredPillContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginVertical: 2,
  },
  sponsoredPill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
    borderWidth: 1,
    borderColor: PALETTE.amber,
  },
  sponsoredPillText: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 10,
    color: PALETTE.amber,
    letterSpacing: 0.5,
  },
  sponsoredCtaBtn: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  sponsoredCtaText: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 11,
    color: '#FFFFFF',
  },
  audioTrackTagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.35)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
    overflow: 'hidden',
    maxWidth: '90%',
  },
  audioTrackTagInner: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  audioTrackTagText: {
    fontFamily: 'Outfit_500Medium',
    fontSize: 12,
    color: 'rgba(255, 255, 255, 0.9)',
  },

  // Pinned Bottom Scrubber
  bottomScrubberContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 48, // Generous Fitts's Law touch target
    justifyContent: 'flex-end',
    zIndex: 20,
  },
  bottomScrubberTrack: {
    width: '100%',
    height: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
  },
  bottomScrubberFill: {
    height: '100%',
    backgroundColor: '#F97316',
    borderRadius: 1.5,
  },

  // Modals & Bottom Sheets
  sheetOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'flex-end',
  },
  sheetContainer: {
    backgroundColor: PALETTE.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingTop: 12,
    paddingBottom: 36,
    paddingHorizontal: 20,
    maxHeight: '65%',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  sheetHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.border,
    alignSelf: 'center',
    marginBottom: 16,
  },
  sheetTitle: {
    fontFamily: 'Outfit_700Bold',
    fontSize: 17,
    color: PALETTE.primary,
    marginBottom: 12,
  },
  sheetFeedbackText: {
    fontFamily: 'Outfit_500Medium',
    fontSize: 13,
    color: PALETTE.lime,
    marginBottom: 10,
  },
  sheetList: {
    marginTop: 6,
  },
  emptyList: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  emptyListText: {
    fontFamily: 'Outfit_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
  },
  threadRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.borderSubtle,
  },
  threadRowPressed: {
    backgroundColor: PALETTE.cardHover,
  },
  threadAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  threadAvatarText: {
    fontFamily: 'Outfit_700Bold',
    fontSize: 15,
    color: PALETTE.primary,
  },
  threadInfo: {
    flex: 1,
  },
  threadName: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 14,
    color: PALETTE.primary,
  },
  threadUsername: {
    fontFamily: 'Outfit_400Regular',
    fontSize: 12,
    color: PALETTE.textSecondary,
  },
  echoChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 14,
    backgroundColor: PALETTE.accent,
  },
  echoChipText: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 12,
    color: '#FFFFFF',
  },

  // Report Modal
  reportModalCard: {
    backgroundColor: PALETTE.surface,
    borderRadius: 20,
    marginHorizontal: 20,
    marginBottom: 'auto',
    marginTop: 'auto',
    padding: 24,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  reportHeading: {
    fontFamily: 'Outfit_700Bold',
    fontSize: 18,
    color: PALETTE.primary,
    marginBottom: 6,
  },
  reportSubheading: {
    fontFamily: 'Outfit_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    marginBottom: 18,
  },
  reportSuccessBox: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  reportSuccessText: {
    fontFamily: 'Outfit_700Bold',
    fontSize: 16,
    color: PALETTE.primary,
    marginTop: 12,
  },
  reportSuccessSubtext: {
    fontFamily: 'Outfit_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    marginTop: 4,
    textAlign: 'center',
  },
  reasonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderRadius: 10,
    marginBottom: 6,
    backgroundColor: PALETTE.card,
  },
  reasonRowActive: {
    backgroundColor: PALETTE.cardHover,
    borderColor: PALETTE.accent,
    borderWidth: 1,
  },
  radioCircle: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: PALETTE.textMuted,
    marginRight: 12,
  },
  radioCircleActive: {
    borderColor: PALETTE.accent,
    backgroundColor: PALETTE.accent,
  },
  reasonText: {
    fontFamily: 'Outfit_500Medium',
    fontSize: 13,
    color: PALETTE.primary,
  },
  reportActionRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
    marginTop: 20,
  },
  cancelBtn: {
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  cancelBtnText: {
    fontFamily: 'Outfit_500Medium',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  submitReportBtn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 12,
    backgroundColor: PALETTE.magenta,
  },
  submitReportText: {
    fontFamily: 'Outfit_600SemiBold',
    fontSize: 14,
    color: '#FFFFFF',
  },
});
