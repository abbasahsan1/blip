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
  FlagMark,
  StatusCheckMark,
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
  const item = (post || propItem) as Blipp;
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

  // ── Engagement telemetry ───────────────────────────────────────────────────
  const { dispatchLike } = useEngagementTelemetry({
    item,
    isPlaying,
    positionSeconds,
    durationSeconds,
    isActive,
  });

  // Like bouncing heart animation
  const heartScale = useRef(new Animated.Value(1)).current;

  const handleLike = async () => {
    Animated.sequence([
      Animated.spring(heartScale, { toValue: 1.5, friction: 3, useNativeDriver: true }),
      Animated.spring(heartScale, { toValue: 1, friction: 4, useNativeDriver: true }),
    ]).start();
    onLike();
    await dispatchLike();
  };

  // ── Dynamic Center Equalizer Visualizer ─────────────────────────────────────
  // 5 animated heights that rhythmically pulse while isPlaying
  const eqBars = useRef([
    new Animated.Value(0.3),
    new Animated.Value(0.6),
    new Animated.Value(0.9),
    new Animated.Value(0.5),
    new Animated.Value(0.2),
  ]).current;
  const eqLoop = useRef<Animated.CompositeAnimation | null>(null);

  // Ambient radial glow animation
  const ambientGlowAnim = useRef(new Animated.Value(0.4)).current;
  const glowLoop = useRef<Animated.CompositeAnimation | null>(null);

  useEffect(() => {
    if (isPlaying) {
      const barAnims = eqBars.map((bar, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(i * 55),
            Animated.timing(bar, {
              toValue: 0.3 + Math.random() * 0.7,
              duration: 220 + Math.random() * 180,
              useNativeDriver: false,
            }),
            Animated.timing(bar, {
              toValue: 0.15 + Math.random() * 0.35,
              duration: 200 + Math.random() * 160,
              useNativeDriver: false,
            }),
          ]),
        ),
      );
      eqLoop.current = Animated.parallel(barAnims);
      eqLoop.current.start();

      glowLoop.current = Animated.loop(
        Animated.sequence([
          Animated.timing(ambientGlowAnim, {
            toValue: 0.9,
            duration: 1200,
            useNativeDriver: false,
          }),
          Animated.timing(ambientGlowAnim, {
            toValue: 0.4,
            duration: 1200,
            useNativeDriver: false,
          }),
        ]),
      );
      glowLoop.current.start();
    } else {
      eqLoop.current?.stop();
      glowLoop.current?.stop();
      eqBars.forEach((bar) => {
        Animated.timing(bar, {
          toValue: 0.25,
          duration: 200,
          useNativeDriver: false,
        }).start();
      });
      Animated.timing(ambientGlowAnim, {
        toValue: 0.25,
        duration: 300,
        useNativeDriver: false,
      }).start();
    }

    return () => {
      eqLoop.current?.stop();
      glowLoop.current?.stop();
    };
  }, [isPlaying, eqBars, ambientGlowAnim]);

  // Scrub bar interaction
  const handleScrub = (event: any) => {
    const layoutWidth = event.nativeEvent.layout?.width || 280;
    const clickX = event.nativeEvent.locationX;
    const ratio = Math.max(0, Math.min(1, clickX / layoutWidth));
    const targetSeconds = Math.floor(ratio * (durationSeconds || 30));
    seekTo(targetSeconds);
  };

  const displayDuration = durationSeconds || item?.duration || 0;

  return (
    <View style={[styles.root, { height }]} testID="audio-reel-card">
      {/* 1. Canvas: Edge-to-edge dark background with ambient radial glow */}
      <View style={styles.canvasBackground} />

      {/* Ambient Pulsing Radial Glow responsive to playback */}
      <Animated.View
        style={[
          styles.ambientRadialGlow,
          {
            opacity: ambientGlowAnim,
            transform: [
              {
                scale: ambientGlowAnim.interpolate({
                  inputRange: [0.2, 1],
                  outputRange: [0.85, 1.25],
                }),
              },
            ],
          },
        ]}
      />

      {/* 2. Center Equalizer Visualizer with Tactile Tap Toggle */}
      <Pressable
        style={styles.centerStage}
        onPress={togglePlayPause}
        accessibilityRole="button"
        accessibilityLabel={isPlaying ? 'Pause broadcast' : 'Play broadcast'}
        testID="center-play-pause-trigger"
      >
        <View style={styles.centerVisualizerBox}>
          {/* Dynamic pulsing audio equalizer bars */}
          <View style={styles.eqCluster}>
            {eqBars.map((bar, idx) => (
              <Animated.View
                key={idx}
                style={[
                  styles.eqBar,
                  {
                    height: bar.interpolate({
                      inputRange: [0, 1],
                      outputRange: ['16%', '100%'],
                    }),
                    backgroundColor: isPlaying ? PALETTE.accent : PALETTE.textMuted,
                  },
                ]}
              />
            ))}
          </View>

          {/* Center tactile play / pause status badge */}
          <View style={[styles.centerPlayBadge, isPlaying && styles.centerPlayBadgePlaying]}>
            {isPlaying ? (
              <PauseMark size={26} color="#FFFFFF" />
            ) : (
              <PlayMark size={28} color="#FFFFFF" />
            )}
          </View>
        </View>
      </Pressable>

      {/* 3. Floating Action Dock (Right Side) */}
      <View style={styles.floatingActionDock} testID="floating-action-dock">
        {/* Like Button (Bouncing heart + count) */}
        <Pressable
          style={({ pressed }) => [
            styles.actionDockPill,
            pressed && styles.dockPillPressed,
          ]}
          onPress={handleLike}
          accessibilityRole="button"
          accessibilityLabel={item?.isLiked ? 'Unlike broadcast' : 'Like broadcast'}
          testID="like-blipp-button"
        >
          <Animated.View style={{ transform: [{ scale: heartScale }] }}>
            <HeartMark
              size={24}
              color={item?.isLiked ? PALETTE.magenta : PALETTE.primary}
              filled={item?.isLiked}
            />
          </Animated.View>
          <Text
            style={[
              styles.dockPillLabel,
              item?.isLiked && { color: PALETTE.magenta },
            ]}
          >
            {formatListens(item?.likeCount || 0)}
          </Text>
        </Pressable>

        {/* Stash / Bookmark Button */}
        <Pressable
          style={({ pressed }) => [
            styles.actionDockPill,
            pressed && styles.dockPillPressed,
          ]}
          onPress={handleSaveToggle}
          disabled={isSaveLoading}
          accessibilityRole="button"
          accessibilityLabel={isSaved ? 'Remove from stash' : 'Stash blipp'}
          testID="save-blipp-button"
        >
          <BookmarkMark
            size={23}
            color={isSaved ? PALETTE.amber : PALETTE.primary}
            filled={isSaved}
          />
          <Text
            style={[
              styles.dockPillLabel,
              isSaved && { color: PALETTE.amber },
            ]}
          >
            {isSaved ? 'Stashed' : 'Stash'}
          </Text>
        </Pressable>

        {/* Echo / DM Share Button */}
        <Pressable
          style={({ pressed }) => [
            styles.actionDockPill,
            pressed && styles.dockPillPressed,
          ]}
          onPress={openShareSheet}
          accessibilityRole="button"
          accessibilityLabel="Echo to direct message"
          testID="share-blipp-button"
        >
          <ShareMark size={22} color={PALETTE.primary} />
          <Text style={styles.dockPillLabel}>Echo</Text>
        </Pressable>

        {/* Report / Flag Button */}
        <Pressable
          style={({ pressed }) => [
            styles.actionDockPill,
            styles.reportPill,
            pressed && styles.dockPillPressed,
          ]}
          onPress={() => setIsReportModalOpen(true)}
          accessibilityRole="button"
          accessibilityLabel="Report broadcast"
          testID="report-content-button"
        >
          <FlagMark size={19} color={PALETTE.textSecondary} />
          <Text style={styles.dockPillLabelMuted}>Report</Text>
        </Pressable>
      </View>

      {/* 4. Bottom Overlay: Creator handle, Follow button, waveform scrub-bar & telemetry */}
      <View style={styles.bottomOverlay} pointerEvents="box-none">
        {/* Creator Attribution & Glowing Follow Button */}
        <View style={styles.creatorRow}>
          <View style={styles.creatorInfo}>
            <View style={styles.avatarGradientCircle}>
              <Text style={styles.avatarInitial}>
                {creatorDisplayName.charAt(0).toUpperCase()}
              </Text>
            </View>
            <View style={styles.creatorTextColumn}>
              <Text style={styles.creatorName} numberOfLines={1}>
                {creatorDisplayName}
              </Text>
              <Text style={styles.creatorHandle} numberOfLines={1}>
                @{creatorHandle}
              </Text>
            </View>
          </View>

          {!isAd && creatorId && (
            <Pressable
              style={({ pressed }) => [
                styles.followBtn,
                isFollowing && styles.followingBtn,
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
                  styles.followBtnText,
                  isFollowing && styles.followingBtnText,
                ]}
              >
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            </Pressable>
          )}
        </View>

        {/* Title & Description */}
        <Text style={styles.trackTitle} numberOfLines={2} testID="blipp-title">
          {item?.title}
        </Text>

        {item?.description ? (
          <Text style={styles.trackDescription} numberOfLines={2}>
            {item.description}
          </Text>
        ) : null}

        {/* Sponsored CTA or Ad Fallback Card */}
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

        {/* Interactive Waveform Scrub-Bar with Live Timestamps */}
        <View style={styles.scrubSection}>
          <Pressable style={styles.scrubTrackArea} onPress={handleScrub}>
            <View style={styles.scrubTrackBg}>
              <View
                style={[
                  styles.scrubTrackProgress,
                  { width: `${Math.max(0, Math.min(100, progress * 100))}%` },
                ]}
              />
            </View>
          </Pressable>

          <View style={styles.timecodeRow}>
            <Text style={styles.timecodeActive}>
              {formatDuration(positionSeconds)}
            </Text>
            <Text style={styles.timecodeDivider}>/</Text>
            <Text style={styles.timecodeTotal}>
              {formatDuration(displayDuration)}
            </Text>
            <Text style={styles.listenCountMeta}>
              • {formatListens(item?.listenCount || 0)} plays
            </Text>
          </View>
        </View>
      </View>

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
                <StatusCheckMark size={32} color={PALETTE.lime} />
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
    width: '100%',
    position: 'relative',
    backgroundColor: PALETTE.bg,
    overflow: 'hidden',
  },
  canvasBackground: {
    ...StyleSheet.absoluteFill,
    backgroundColor: PALETTE.bg,
  },
  ambientRadialGlow: {
    position: 'absolute',
    top: '32%',
    left: '25%',
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: PALETTE.accentGlow,
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 60,
  },
  centerStage: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'center',
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
    height: 80,
    gap: 7,
    marginBottom: 12,
  },
  eqBar: {
    width: 6,
    borderRadius: 3,
    backgroundColor: PALETTE.accent,
  },
  centerPlayBadge: {
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: 'rgba(17, 19, 27, 0.75)',
    borderWidth: 1.5,
    borderColor: 'rgba(255, 255, 255, 0.18)',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 14,
  },
  centerPlayBadgePlaying: {
    borderColor: PALETTE.accentGlow,
    backgroundColor: 'rgba(124, 58, 237, 0.25)',
  },

  // Floating Action Dock (Right Side)
  floatingActionDock: {
    position: 'absolute',
    right: 14,
    bottom: 120,
    alignItems: 'center',
    gap: 16,
    zIndex: 10,
  },
  actionDockPill: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: PALETTE.cardGlass,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.09)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.45,
    shadowRadius: 10,
  },
  dockPillPressed: {
    transform: [{ scale: 0.92 }],
    backgroundColor: PALETTE.cardHover,
  },
  dockPillLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 10,
    color: PALETTE.primary,
    marginTop: 2,
  },
  dockPillLabelMuted: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 9,
    color: PALETTE.textSecondary,
    marginTop: 2,
  },
  reportPill: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(17, 19, 27, 0.65)',
  },

  // Bottom Overlay
  bottomOverlay: {
    position: 'absolute',
    left: 0,
    right: 76,
    bottom: 24,
    paddingHorizontal: 20,
    zIndex: 8,
  },
  creatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  creatorInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
  },
  avatarGradientCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: PALETTE.borderGlass,
  },
  avatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 16,
    color: '#FFFFFF',
  },
  creatorTextColumn: {
    flex: 1,
  },
  creatorName: {
    fontFamily: 'Sora_700Bold',
    fontSize: 15,
    color: PALETTE.primary,
    letterSpacing: -0.3,
  },
  creatorHandle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textSecondary,
  },
  followBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 18,
    backgroundColor: PALETTE.accent,
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 8,
  },
  followingBtn: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: PALETTE.accent,
    shadowOpacity: 0,
  },
  followBtnPressed: {
    opacity: 0.8,
  },
  followBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: '#FFFFFF',
  },
  followingBtnText: {
    color: PALETTE.accent,
  },
  trackTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.primary,
    lineHeight: 24,
    marginBottom: 4,
    letterSpacing: -0.4,
  },
  trackDescription: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    lineHeight: 18,
    marginBottom: 8,
  },
  sponsoredPillContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
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
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 10,
    color: PALETTE.amber,
    letterSpacing: 0.5,
  },
  sponsoredCtaBtn: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  sponsoredCtaText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 11,
    color: PALETTE.primary,
  },

  // Waveform Scrub-Bar
  scrubSection: {
    marginTop: 6,
  },
  scrubTrackArea: {
    paddingVertical: 6,
  },
  scrubTrackBg: {
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    overflow: 'hidden',
  },
  scrubTrackProgress: {
    height: '100%',
    backgroundColor: PALETTE.accent,
    borderRadius: 2,
  },
  timecodeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
  },
  timecodeActive: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 11,
    color: PALETTE.accent,
  },
  timecodeDivider: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
    marginHorizontal: 3,
  },
  timecodeTotal: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  listenCountMeta: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
    marginLeft: 6,
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
    fontFamily: 'Sora_700Bold',
    fontSize: 17,
    color: PALETTE.primary,
    marginBottom: 12,
  },
  sheetFeedbackText: {
    fontFamily: 'PlusJakartaSans_500Medium',
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
    fontFamily: 'PlusJakartaSans_400Regular',
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
    fontFamily: 'Sora_700Bold',
    fontSize: 15,
    color: PALETTE.primary,
  },
  threadInfo: {
    flex: 1,
  },
  threadName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.primary,
  },
  threadUsername: {
    fontFamily: 'PlusJakartaSans_400Regular',
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
    fontFamily: 'PlusJakartaSans_600SemiBold',
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
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.primary,
    marginBottom: 6,
  },
  reportSubheading: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    marginBottom: 18,
  },
  reportSuccessBox: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  reportSuccessText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 16,
    color: PALETTE.primary,
    marginTop: 12,
  },
  reportSuccessSubtext: {
    fontFamily: 'PlusJakartaSans_400Regular',
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
    fontFamily: 'PlusJakartaSans_500Medium',
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
    fontFamily: 'PlusJakartaSans_500Medium',
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
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#FFFFFF',
  },
});
