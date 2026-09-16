/**
 * AudioReel
 *
 * Full-bleed, edge-to-edge dark audio card for the Blipp feed.
 * Restrained product design:
 *   - Minimal dark canvas
 *   - Simple center play/pause indicator
 *   - Clean action column (no floating glass effects)
 *   - Left-aligned metadata
 *   - Unobtrusive scrubber
 */

import { useState, useEffect } from 'react';
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
import { Feather } from '@expo/vector-icons';
import { useAudioPlayer } from '@/lib/audio/useAudioPlayer';
import { useAudioPrefetch } from '@/lib/audio/useAudioPrefetch';
import { api, resolveMediaUrl } from '@/lib/api';
import type { AudioPost, Blipp, DMThreadItem } from '@/lib/types';
import { theme } from '@/lib/theme';

// ─── Utilities ────────────────────────────────────────────────────────────────

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
  onSave?: () => Promise<void> | void;
  onFollow?: () => Promise<void> | void;
  onAutoSkip?: () => void;
  feedItems?: Blipp[];
  activeIndex?: number;
  shouldLoad?: boolean;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function AudioReel({
  post,
  item: propItem,
  isActive,
  height,
  onLike,
  onSave,
  onFollow,
  onAutoSkip,
  feedItems = [],
  activeIndex = 0,
  shouldLoad = true,
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

  const isSaved = Boolean(item?.is_saved);
  const isFollowing = Boolean(item?.is_following);

  const handleSaveToggle = async () => {
    if (onSave) await onSave();
  };

  const handleFollowToggle = async () => {
    if (onFollow) await onFollow();
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
      setShareFeedback(`Shared to ${name}!`);
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

  const { getCachedUri } = useAudioPrefetch({
    items: feedItems,
    activeIndex,
    enabled: isActive,
  });
  const localUri = blippId ? getCachedUri(blippId) : null;

  const {
    isPlaying,
    durationSeconds,
    progress,
    togglePlayPause,
    seekTo,
    isAdFallback,
    adCountdown,
  } = useAudioPlayer({ item, isActive, localUri, shouldLoad });

  useEffect(() => {
    if (isAdFallback && isActive && adCountdown <= 0) {
      onAutoSkip?.();
    }
  }, [isAdFallback, isActive, adCountdown, onAutoSkip]);

  const handleLike = async () => {
    await onLike();
  };

  const handleScrub = (event: any) => {
    const layoutWidth = event.nativeEvent.layout?.width || Dimensions.get('window').width;
    const clickX = event.nativeEvent.locationX;
    const ratio = Math.max(0, Math.min(1, clickX / layoutWidth));
    const targetSeconds = Math.floor(ratio * (durationSeconds || 1));
    seekTo(targetSeconds);
  };

  const reelHeight = height || Dimensions.get('window').height;

  return (
    <View style={[styles.root, { height: reelHeight }]} testID="audio-reel-card">
      <View style={styles.canvasBackground} />

      <Pressable
        style={styles.centerStage}
        onPress={togglePlayPause}
        accessibilityRole="button"
        accessibilityLabel={isPlaying ? 'Pause' : 'Play'}
        testID="center-play-pause-trigger"
      >
        <View style={styles.centerPlayBadge}>
          {isPlaying ? (
            <Feather name="pause" size={32} color={theme.colors.text} />
          ) : (
            <Feather name="play" size={32} color={theme.colors.text} style={{ marginLeft: 4 }} />
          )}
        </View>
      </Pressable>

      {/* Right Column Actions */}
      <View style={styles.actionColumn} testID="floating-action-dock">
        <View style={styles.profileItem}>
          {item?.creator?.avatar_url || (item as any)?.avatar_url ? (
            <Image
              source={{ uri: item?.creator?.avatar_url || (item as any)?.avatar_url }}
              style={styles.profilePicture}
              accessibilityLabel={`${creatorDisplayName}'s profile`}
            />
          ) : (
            <View style={styles.profileFallback}>
              <Text style={styles.profileInitial}>{creatorDisplayName.slice(0, 1).toUpperCase()}</Text>
            </View>
          )}
        </View>

        <Pressable
          style={({ pressed }) => [styles.actionButton, pressed && styles.actionButtonPressed]}
          onPress={handleLike}
          accessibilityRole="button"
          accessibilityLabel={item?.isLiked ? 'Unlike' : 'Like'}
          testID="like-blipp-button"
        >
          <Feather name="heart" size={28} color={item?.isLiked ? theme.colors.error : theme.colors.text} />
          <Text style={[styles.actionText, item?.isLiked && { color: theme.colors.error }]}>
            {formatListens(item?.likeCount || 0)}
          </Text>
        </Pressable>

        <Pressable
          style={({ pressed }) => [styles.actionButton, pressed && styles.actionButtonPressed]}
          onPress={handleSaveToggle}
          accessibilityRole="button"
          accessibilityLabel={isSaved ? 'Unsave' : 'Save'}
          testID="save-blipp-button"
        >
          <Feather name="bookmark" size={28} color={isSaved ? theme.colors.primary : theme.colors.text} />
          <Text style={[styles.actionText, isSaved && { color: theme.colors.primary }]}>
            {isSaved ? 'Saved' : 'Save'}
          </Text>
        </Pressable>

        <Pressable
          style={({ pressed }) => [styles.actionButton, pressed && styles.actionButtonPressed]}
          onPress={openShareSheet}
          accessibilityRole="button"
          accessibilityLabel="Share"
          testID="share-blipp-button"
        >
          <Feather name="send" size={28} color={theme.colors.text} />
          <Text style={styles.actionText}>Share</Text>
        </Pressable>

        <Pressable
          style={({ pressed }) => [styles.actionButton, pressed && styles.actionButtonPressed]}
          onPress={() => setIsReportModalOpen(true)}
          accessibilityRole="button"
          accessibilityLabel="Options"
          testID="report-content-button"
        >
          <Feather name="more-horizontal" size={28} color={theme.colors.text} />
        </Pressable>
      </View>

      {/* Bottom Metadata */}
      <View style={styles.metadataDock} pointerEvents="box-none">
        <View style={styles.creatorRow}>
          <Text style={styles.creatorHandle} numberOfLines={1}>
            @{creatorHandle}
          </Text>
          <Feather name="check-circle" size={14} color={theme.colors.primary} />
          
          {!isAd && creatorId && (
            <Pressable
              style={styles.followButton}
              onPress={handleFollowToggle}
              accessibilityRole="button"
              accessibilityLabel={isFollowing ? 'Unfollow' : 'Follow'}
              testID="follow-creator-button"
            >
              <Text style={styles.followButtonText}>
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            </Pressable>
          )}
        </View>

        <Text style={styles.title} numberOfLines={2} testID="blipp-title">
          {item?.title}
        </Text>

        {item?.description ? (
          <Text style={styles.description} numberOfLines={2}>
            {item.description}
          </Text>
        ) : null}

        {isAd && (
          <View style={styles.adPill}>
            <Text style={styles.adPillText}>SPONSORED</Text>
            {item?.sponsor?.cta_url && (
              <Pressable
                style={styles.adCta}
                onPress={() => item.sponsor?.cta_url && Linking.openURL(item.sponsor.cta_url)}
              >
                <Text style={styles.adCtaText}>{item.sponsor.cta_text || 'Learn More'}</Text>
              </Pressable>
            )}
          </View>
        )}
      </View>

      {/* Scrubber */}
      <Pressable
        style={styles.scrubberContainer}
        onPress={handleScrub}
        testID="bottom-scrubber-bar"
      >
        <View style={styles.scrubberTrack}>
          <Animated.View
            style={[
              styles.scrubberFill,
              { 
                width: progress.interpolate({
                  inputRange: [0, 1],
                  outputRange: ['0%', '100%']
                }) 
              },
            ]}
          />
        </View>
      </Pressable>

      {/* Modals omitted for brevity but keeping their basic structure intact */}
      <Modal visible={isShareModalOpen} transparent animationType="slide" onRequestClose={() => setIsShareModalOpen(false)}>
        <Pressable style={styles.modalOverlay} onPress={() => setIsShareModalOpen(false)}>
          <Pressable style={styles.modalContent} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Share Blipp</Text>
            {shareFeedback && <Text style={styles.feedbackText}>{shareFeedback}</Text>}
            <FlatList
              data={shareThreads}
              keyExtractor={(t) => t.thread_id}
              ListEmptyComponent={<Text style={styles.emptyText}>No recent conversations</Text>}
              renderItem={({ item: thread }) => (
                <Pressable
                  style={styles.threadRow}
                  onPress={() => handleShareToThread(thread.thread_id, thread.other_participant?.username || 'user')}
                  disabled={isSharing}
                >
                  <Text style={styles.threadText}>@{thread.other_participant?.username}</Text>
                  <Text style={styles.sendText}>Send</Text>
                </Pressable>
              )}
            />
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={isReportModalOpen} transparent animationType="fade" onRequestClose={() => setIsReportModalOpen(false)}>
        <Pressable style={styles.modalOverlay} onPress={() => setIsReportModalOpen(false)}>
          <Pressable style={styles.modalContent} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Report Content</Text>
            {reportSubmitted ? (
              <Text style={styles.feedbackText}>Thank you for your report.</Text>
            ) : (
              <>
                {['inappropriate', 'harassment', 'spam', 'copyright'].map((reason) => (
                  <Pressable
                    key={reason}
                    style={styles.reasonRow}
                    onPress={() => setReportReason(reason)}
                  >
                    <Feather name={reportReason === reason ? 'check-circle' : 'circle'} size={20} color={theme.colors.text} />
                    <Text style={styles.reasonText}>{reason}</Text>
                  </Pressable>
                ))}
                <Pressable style={styles.submitButton} onPress={handleReportSubmit} disabled={isSubmittingReport}>
                  <Text style={styles.submitButtonText}>Submit Report</Text>
                </Pressable>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    width: '100%',
    position: 'relative',
    backgroundColor: theme.colors.background,
    overflow: 'hidden',
  },
  canvasBackground: {
    ...StyleSheet.absoluteFill,
    backgroundColor: theme.colors.background,
  },
  centerStage: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 2,
  },
  centerPlayBadge: {
    width: 80,
    height: 80,
    borderRadius: theme.radius.full,
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionColumn: {
    position: 'absolute',
    right: theme.spacing.lg,
    bottom: 80,
    alignItems: 'center',
    gap: theme.spacing.xl,
    zIndex: 10,
  },
  profileItem: {
    marginBottom: theme.spacing.sm,
  },
  profilePicture: {
    width: 48,
    height: 48,
    borderRadius: theme.radius.full,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  profileFallback: {
    width: 48,
    height: 48,
    borderRadius: theme.radius.full,
    backgroundColor: theme.colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  profileInitial: {
    ...theme.typography.title,
    color: theme.colors.text,
  },
  actionButton: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: theme.spacing.xs,
  },
  actionButtonPressed: {
    opacity: 0.6,
  },
  actionText: {
    ...theme.typography.metadata,
    color: theme.colors.text,
  },
  metadataDock: {
    position: 'absolute',
    bottom: 24,
    left: theme.spacing.lg,
    right: 80,
    zIndex: 10,
    gap: theme.spacing.sm,
  },
  creatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
  },
  creatorHandle: {
    ...theme.typography.bodySemibold,
    color: theme.colors.text,
  },
  followButton: {
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radius.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    marginLeft: theme.spacing.xs,
  },
  followButtonText: {
    ...theme.typography.metadata,
    color: theme.colors.text,
  },
  title: {
    ...theme.typography.title,
    color: theme.colors.text,
  },
  description: {
    ...theme.typography.caption,
    color: theme.colors.textMuted,
  },
  adPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  adPillText: {
    ...theme.typography.metadata,
    color: theme.colors.primary,
  },
  adCta: {
    backgroundColor: theme.colors.surface,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.radius.sm,
  },
  adCtaText: {
    ...theme.typography.captionSemibold,
    color: theme.colors.text,
  },
  scrubberContainer: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: 16,
    justifyContent: 'flex-end',
    zIndex: 20,
  },
  scrubberTrack: {
    height: 2,
    backgroundColor: theme.colors.surface,
    width: '100%',
  },
  scrubberFill: {
    height: '100%',
    backgroundColor: theme.colors.primary,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: theme.colors.background,
    borderTopLeftRadius: theme.radius.md,
    borderTopRightRadius: theme.radius.md,
    padding: theme.spacing.xxl,
    minHeight: 300,
  },
  modalTitle: {
    ...theme.typography.title,
    color: theme.colors.text,
    marginBottom: theme.spacing.lg,
  },
  feedbackText: {
    ...theme.typography.body,
    color: theme.colors.primary,
    marginBottom: theme.spacing.lg,
  },
  emptyText: {
    ...theme.typography.body,
    color: theme.colors.textMuted,
  },
  threadRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: theme.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  threadText: {
    ...theme.typography.body,
    color: theme.colors.text,
  },
  sendText: {
    ...theme.typography.button,
    color: theme.colors.primary,
  },
  reasonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  reasonText: {
    ...theme.typography.body,
    color: theme.colors.text,
  },
  submitButton: {
    backgroundColor: theme.colors.primary,
    padding: theme.spacing.md,
    borderRadius: theme.radius.md,
    alignItems: 'center',
    marginTop: theme.spacing.lg,
  },
  submitButtonText: {
    ...theme.typography.button,
    color: theme.colors.background,
  },
});
