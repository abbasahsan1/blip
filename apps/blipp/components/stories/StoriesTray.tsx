import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  Image,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { PALETTE } from '@/lib/palette';
import { PlayMark, PauseMark } from '@/components/common/Icons';
import { api, resolvePublicAudioUrl } from '@/lib/api';
import type { StoryItem } from '@/lib/types';

function formatExpiresIn(expiresAt: string): string {
  try {
    const diffMs = new Date(expiresAt).getTime() - Date.now();
    if (diffMs <= 0) return 'Expired';
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    if (hours > 0) return `${hours}h left`;
    const mins = Math.floor(diffMs / (1000 * 60));
    return `${mins}m left`;
  } catch {
    return '24h story';
  }
}

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function StoriesTray() {
  const [stories, setStories] = useState<StoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeStory, setActiveStory] = useState<StoryItem | null>(null);

  // Audio playback state for modal player
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Animated visualizer bars in story modal
  const visualizerBars = useRef(
    Array.from({ length: 24 }, () => new Animated.Value(0.2)),
  ).current;
  const animRef = useRef<Animated.CompositeAnimation | null>(null);

  const fetchStories = useCallback(async () => {
    setIsLoading(true);
    try {
      const items = await api.getStories();
      setStories(items || []);
    } catch {
      // Non-blocking fallback
      setStories([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStories();
  }, [fetchStories]);

  // Handle active story audio playback
  useEffect(() => {
    if (!activeStory) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
        audioRef.current = null;
      }
      setIsPlaying(false);
      setProgress(0);
      setCurrentTime(0);
      setDuration(0);
      return;
    }

    if (typeof window === 'undefined' || typeof Audio === 'undefined') return;

    const audioUrl = resolvePublicAudioUrl(activeStory.audio_url);
    const audio = new Audio(audioUrl);
    audioRef.current = audio;

    const onLoadedMetadata = () => {
      setDuration(audio.duration || activeStory.duration_seconds || 0);
    };

    const onTimeUpdate = () => {
      const cur = audio.currentTime || 0;
      const dur = audio.duration || activeStory.duration_seconds || 1;
      setCurrentTime(cur);
      setProgress(Math.min(1, cur / dur));
    };

    const onEnded = () => {
      setIsPlaying(false);
      setProgress(1);
    };

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    audio.addEventListener('loadedmetadata', onLoadedMetadata);
    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);

    audio.play().catch(() => {
      setIsPlaying(false);
    });

    return () => {
      audio.removeEventListener('loadedmetadata', onLoadedMetadata);
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      audio.pause();
      audio.src = '';
      audioRef.current = null;
    };
  }, [activeStory]);

  // Visualizer loop when playing
  useEffect(() => {
    if (isPlaying) {
      const anims = visualizerBars.map((bar, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(i * 30),
            Animated.timing(bar, {
              toValue: 0.3 + Math.random() * 0.7,
              duration: 200 + Math.random() * 200,
              useNativeDriver: false,
            }),
            Animated.timing(bar, {
              toValue: 0.15 + Math.random() * 0.2,
              duration: 200 + Math.random() * 200,
              useNativeDriver: false,
            }),
          ]),
        ),
      );
      animRef.current = Animated.parallel(anims);
      animRef.current.start();
    } else {
      animRef.current?.stop();
      visualizerBars.forEach((b) =>
        Animated.timing(b, {
          toValue: 0.2,
          duration: 150,
          useNativeDriver: false,
        }).start(),
      );
    }

    return () => {
      animRef.current?.stop();
    };
  }, [isPlaying, visualizerBars]);

  const toggleModalPlayback = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(() => {});
    }
  };

  const closeModal = () => {
    setActiveStory(null);
  };

  if (stories.length === 0 && !isLoading) {
    return null;
  }

  return (
    <View style={styles.container} testID="stories-tray">
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {stories.map((story) => {
          const creatorName =
            story.creator?.display_name ||
            story.creator?.username ||
            `Creator ${story.creator_id.slice(0, 6)}`;
          const initial = creatorName.charAt(0).toUpperCase();

          return (
            <Pressable
              key={story.story_id}
              style={styles.avatarCard}
              onPress={() => setActiveStory(story)}
              accessibilityRole="button"
              accessibilityLabel={`Play story by ${creatorName}`}
              testID={`story-avatar-${story.story_id}`}
            >
              {/* Circular avatar with unread accent ring */}
              <View style={styles.accentRing}>
                <View style={styles.avatarInner}>
                  {story.creator?.avatar_url ? (
                    <Image
                      source={{ uri: story.creator.avatar_url }}
                      style={styles.avatarImage}
                    />
                  ) : (
                    <View style={styles.initialFallback}>
                      <Text style={styles.initialText}>{initial}</Text>
                    </View>
                  )}
                </View>
              </View>
              <Text style={styles.creatorLabel} numberOfLines={1}>
                {creatorName}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {/* Ephemeral Story Modal Audio Player */}
      <Modal
        visible={Boolean(activeStory)}
        animationType="fade"
        transparent
        onRequestClose={closeModal}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalBackdrop} />

          <View style={styles.modalCard} testID="story-modal-player">
            {/* Story Timeline Progress Bar */}
            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${Math.round(progress * 100)}%` },
                ]}
              />
            </View>

            {/* Header: Creator details & Close (X) button */}
            <View style={styles.modalHeader}>
              <View style={styles.modalCreatorInfo}>
                <View style={styles.modalSmallRing}>
                  {activeStory?.creator?.avatar_url ? (
                    <Image
                      source={{ uri: activeStory.creator.avatar_url }}
                      style={styles.modalSmallAvatar}
                    />
                  ) : (
                    <View style={styles.modalSmallInitial}>
                      <Text style={styles.modalSmallInitialText}>
                        {(
                          activeStory?.creator?.display_name ||
                          activeStory?.creator?.username ||
                          'C'
                        )
                          .charAt(0)
                          .toUpperCase()}
                      </Text>
                    </View>
                  )}
                </View>
                <View>
                  <Text style={styles.modalCreatorName} numberOfLines={1}>
                    {activeStory?.creator?.display_name ||
                      activeStory?.creator?.username ||
                      'Creator'}
                  </Text>
                  <Text style={styles.modalExpiresText}>
                    {activeStory ? formatExpiresIn(activeStory.expires_at) : '24h story'}
                  </Text>
                </View>
              </View>

              <Pressable
                style={({ pressed }) => [
                  styles.closeBtn,
                  pressed && styles.closeBtnPressed,
                ]}
                onPress={closeModal}
                accessibilityRole="button"
                accessibilityLabel="Close story"
                testID="close-story-button"
              >
                <Text style={styles.closeBtnText}>✕</Text>
              </Pressable>
            </View>

            {/* Animated Waveform Deck */}
            <View style={styles.visualizerContainer}>
              <View style={styles.visualizerBars}>
                {visualizerBars.map((bar, i) => {
                  const barProgress = i / visualizerBars.length;
                  const passed = barProgress <= progress;
                  return (
                    <Animated.View
                      key={i}
                      style={[
                        styles.visualizerBar,
                        {
                          height: bar.interpolate({
                            inputRange: [0, 1],
                            outputRange: ['10%', '100%'],
                          }),
                          backgroundColor: passed ? PALETTE.accent : '#3f3f46',
                          opacity: isPlaying ? 1 : 0.4,
                        },
                      ]}
                    />
                  );
                })}
              </View>
            </View>

            {/* Playback Controls & Timecode */}
            <View style={styles.modalControls}>
              <Pressable
                style={({ pressed }) => [
                  styles.modalPlayBtn,
                  pressed && styles.modalPlayBtnPressed,
                ]}
                onPress={toggleModalPlayback}
                accessibilityRole="button"
                accessibilityLabel={isPlaying ? 'Pause story' : 'Play story'}
                testID="story-play-button"
              >
                {isPlaying ? (
                  <PauseMark size={22} color="#ffffff" />
                ) : (
                  <PlayMark size={22} color="#ffffff" />
                )}
              </Pressable>

              <View style={styles.modalTimecode}>
                <Text style={styles.timecodeText}>
                  {formatDuration(currentTime)} / {formatDuration(duration || activeStory?.duration_seconds || 0)}
                </Text>
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 8,
    backgroundColor: PALETTE.bg,
    justifyContent: 'center',
  },
  scrollContent: {
    paddingHorizontal: 16,
    alignItems: 'center',
    gap: 14,
  },
  avatarCard: {
    alignItems: 'center',
    width: 66,
    gap: 5,
  },
  accentRing: {
    width: 58,
    height: 58,
    borderRadius: 29,
    borderWidth: 2,
    borderColor: PALETTE.accent,
    padding: 2,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: PALETTE.surface,
  },
  avatarInner: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#1e1b4b',
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarImage: {
    width: '100%',
    height: '100%',
  },
  initialFallback: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#312e81',
  },
  initialText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: '#ffffff',
  },
  creatorLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    maxWidth: 64,
  },
  // Modal Player Styles
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(9, 9, 11, 0.88)',
  },
  modalCard: {
    width: '100%',
    maxWidth: 420,
    backgroundColor: PALETTE.card,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    padding: 20,
    gap: 20,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.5,
    shadowRadius: 20,
    elevation: 12,
  },
  progressTrack: {
    width: '100%',
    height: 3,
    backgroundColor: PALETTE.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: PALETTE.accent,
    borderRadius: 2,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  modalCreatorInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
  },
  modalSmallRing: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1.5,
    borderColor: PALETTE.accent,
    padding: 1.5,
  },
  modalSmallAvatar: {
    width: '100%',
    height: '100%',
    borderRadius: 18,
  },
  modalSmallInitial: {
    width: '100%',
    height: '100%',
    borderRadius: 18,
    backgroundColor: '#312e81',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalSmallInitialText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 14,
    color: '#ffffff',
  },
  modalCreatorName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  modalExpiresText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: PALETTE.surface,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  closeBtnPressed: {
    backgroundColor: PALETTE.cardHover,
  },
  closeBtnText: {
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  visualizerContainer: {
    height: 90,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: PALETTE.surface,
    borderRadius: 10,
    paddingHorizontal: 16,
  },
  visualizerBars: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 60,
    gap: 4,
    width: '100%',
    justifyContent: 'center',
  },
  visualizerBar: {
    flex: 1,
    maxWidth: 8,
    borderRadius: 3,
  },
  modalControls: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 4,
  },
  modalPlayBtn: {
    width: 50,
    height: 50,
    borderRadius: 10,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalPlayBtnPressed: {
    opacity: 0.85,
  },
  modalTimecode: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  timecodeText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13,
    color: PALETTE.textSecondary,
    fontVariant: ['tabular-nums'],
  },
});
