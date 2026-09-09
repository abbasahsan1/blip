/**
 * StoryModal
 *
 * Full-screen 24-hour audio story viewer (§5.4).
 * Plays the creator's audio clip using expo-av Audio.Sound (with web fallback).
 * Features:
 *   - Segmented progress bar across creator stories
 *   - Creator avatar, display name, @username, and relative expiration time
 *   - Staggered waveform visualizer bars pulsing with playback
 *   - Tap left half for previous, tap right half for next
 *   - Auto-advances to next creator story on playback completion
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Animated,
  Dimensions,
  Image,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  createAudioPlayer,
  setAudioModeAsync,
  type AudioPlayer,
  type AudioStatus,
} from 'expo-audio';
import { PALETTE } from '@/lib/palette';
import { PlayMark, PauseMark } from '@/components/common/Icons';
import { resolvePublicAudioUrl } from '@/lib/api';
import type { StoryItem } from '@/lib/types';

interface Props {
  stories: StoryItem[];
  initialIndex?: number;
  visible: boolean;
  onClose: () => void;
}

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

export function StoryModal({
  stories,
  initialIndex = 0,
  visible,
  onClose,
}: Props) {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [positionSeconds, setPositionSeconds] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(0);

  const playerRef = useRef<AudioPlayer | null>(null);
  const playerSubRef = useRef<{ remove: () => void } | null>(null);
  const webAudioRef = useRef<HTMLAudioElement | null>(null);

  // Synchronize initialIndex when opening modal
  useEffect(() => {
    if (visible) {
      setCurrentIndex(Math.max(0, Math.min(initialIndex, stories.length - 1)));
      setProgress(0);
      setPositionSeconds(0);
    }
  }, [visible, initialIndex, stories.length]);

  const currentStory = stories[currentIndex] || null;

  // Visualizer animated bars
  const bars = useRef(
    Array.from({ length: 28 }, () => new Animated.Value(0.2)),
  ).current;
  const animRef = useRef<Animated.CompositeAnimation | null>(null);

  useEffect(() => {
    if (isPlaying) {
      const anims = bars.map((bar, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(i * 25),
            Animated.timing(bar, {
              toValue: 0.25 + Math.random() * 0.75,
              duration: 220 + Math.random() * 220,
              useNativeDriver: false,
            }),
            Animated.timing(bar, {
              toValue: 0.12 + Math.random() * 0.2,
              duration: 220 + Math.random() * 180,
              useNativeDriver: false,
            }),
          ]),
        ),
      );
      animRef.current = Animated.parallel(anims);
      animRef.current.start();
    } else {
      animRef.current?.stop();
      bars.forEach((b) =>
        Animated.timing(b, {
          toValue: 0.2,
          duration: 160,
          useNativeDriver: false,
        }).start(),
      );
    }

    return () => {
      animRef.current?.stop();
    };
  }, [isPlaying, bars]);

  // Navigate to next story or finish
  const handleNextStory = useCallback(() => {
    if (currentIndex < stories.length - 1) {
      setProgress(0);
      setPositionSeconds(0);
      setCurrentIndex((prev) => prev + 1);
    } else {
      onClose();
    }
  }, [currentIndex, stories.length, onClose]);

  // Navigate to previous story
  const handlePrevStory = useCallback(() => {
    if (currentIndex > 0) {
      setProgress(0);
      setPositionSeconds(0);
      setCurrentIndex((prev) => prev - 1);
    } else {
      setProgress(0);
      setPositionSeconds(0);
    }
  }, [currentIndex]);

  // Audio setup and playback
  useEffect(() => {
    if (!visible || !currentStory) {
      cleanupAudio();
      return;
    }

    let isMounted = true;
    const rawAudioUrl = currentStory.audio_url;
    const publicUrl = resolvePublicAudioUrl(rawAudioUrl);
    async function loadAudio() {
      cleanupAudio();

      if (!publicUrl) return;

      try {
        await setAudioModeAsync({
          playsInSilentMode: true,
          shouldPlayInBackground: false,
        }).catch(() => {});

        const player = createAudioPlayer(publicUrl);
        playerRef.current = player;

        const sub = (player as any).addListener(
          'playbackStatusUpdate',
          (status: AudioStatus) => {
          if (!isMounted) return;
          setIsPlaying(status.playing);
          const posSec = status.currentTime || 0;
          const durSec =
            status.duration || currentStory?.duration_seconds || 15;
          setPositionSeconds(posSec);
          setDurationSeconds(durSec);
          setProgress(durSec > 0 ? Math.min(1, posSec / durSec) : 0);

          if (status.didJustFinish) {
            handleNextStory();
          }
        });
        playerSubRef.current = sub;

        player.play();
        if (isMounted) setIsPlaying(true);
      } catch {
        // Fallback to HTML5 Audio on Web if createAudioPlayer failed or in web environment
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          const audio = new window.Audio(publicUrl);
          webAudioRef.current = audio;

          audio.onloadedmetadata = () => {
            if (!isMounted) return;
            setDurationSeconds(audio.duration || currentStory?.duration_seconds || 15);
          };

          audio.ontimeupdate = () => {
            if (!isMounted) return;
            const cur = audio.currentTime || 0;
            const dur = audio.duration || currentStory?.duration_seconds || 15;
            setPositionSeconds(cur);
            setProgress(Math.min(1, cur / dur));
          };

          audio.onended = () => {
            if (!isMounted) return;
            setIsPlaying(false);
            setProgress(1);
            handleNextStory();
          };

          audio.onplay = () => {
            if (isMounted) setIsPlaying(true);
          };
          audio.onpause = () => {
            if (isMounted) setIsPlaying(false);
          };

          audio.play().catch(() => {
            if (isMounted) setIsPlaying(false);
          });
        }
      }
    }

    void loadAudio();

    return () => {
      isMounted = false;
      cleanupAudio();
    };
  }, [visible, currentIndex, currentStory?.audio_url]);

  const cleanupAudio = () => {
    if (playerSubRef.current) {
      try {
        playerSubRef.current.remove();
      } catch {}
      playerSubRef.current = null;
    }
    if (playerRef.current) {
      try {
        playerRef.current.pause();
        if (typeof (playerRef.current as any).release === 'function') {
          (playerRef.current as any).release();
        } else if (typeof (playerRef.current as any).remove === 'function') {
          (playerRef.current as any).remove();
        }
      } catch {}
      playerRef.current = null;
    }
    if (webAudioRef.current) {
      webAudioRef.current.pause();
      webAudioRef.current.src = '';
      webAudioRef.current = null;
    }
    setIsPlaying(false);
    setProgress(0);
    setPositionSeconds(0);
  };

  const togglePlayPause = async () => {
    if (playerRef.current) {
      if (isPlaying) {
        playerRef.current.pause();
        setIsPlaying(false);
      } else {
        playerRef.current.play();
        setIsPlaying(true);
      }
    } else if (webAudioRef.current) {
      if (isPlaying) {
        webAudioRef.current.pause();
        setIsPlaying(false);
      } else {
        webAudioRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
    }
  };;

  if (!visible || !currentStory) {
    return null;
  }

  const creatorName =
    currentStory.creator?.display_name ||
    currentStory.creator?.username ||
    `Creator ${currentStory.creator_id.slice(0, 6)}`;
  const username = currentStory.creator?.username
    ? `@${currentStory.creator.username}`
    : '';
  const initial = creatorName.charAt(0).toUpperCase();

  return (
    <Modal
      visible={visible}
      animationType="fade"
      transparent
      onRequestClose={onClose}
    >
      <View style={styles.container} testID="story-modal-viewer">
        {/* Fullscreen backdrop with rich dark studio theme */}
        <View style={styles.backdrop} />

        {/* Segmented Top Progress Indicators */}
        <View style={styles.segmentedProgressRow}>
          {stories.map((s, idx) => {
            let segProgress = 0;
            if (idx < currentIndex) segProgress = 1;
            else if (idx === currentIndex) segProgress = progress;
            else segProgress = 0;

            return (
              <View key={s.story_id} style={styles.segmentTrack}>
                <View
                  style={[
                    styles.segmentFill,
                    { width: `${Math.round(segProgress * 100)}%` },
                  ]}
                />
              </View>
            );
          })}
        </View>

        {/* Top Header Row: Creator Avatar, Names, Expiration, Close Button */}
        <View style={styles.headerRow}>
          <View style={styles.creatorInfo}>
            <View style={styles.avatarRing}>
              {currentStory.creator?.avatar_url ? (
                <Image
                  source={{ uri: currentStory.creator.avatar_url }}
                  style={styles.avatarImage}
                />
              ) : (
                <View style={styles.initialFallback}>
                  <Text style={styles.initialText}>{initial}</Text>
                </View>
              )}
            </View>
            <View style={styles.nameBlock}>
              <View style={styles.titleLine}>
                <Text style={styles.creatorName} numberOfLines={1}>
                  {creatorName}
                </Text>
                {username ? (
                  <Text style={styles.usernameText} numberOfLines={1}>
                    {username}
                  </Text>
                ) : null}
              </View>
              <Text style={styles.expiresText}>
                {formatExpiresIn(currentStory.expires_at)}
              </Text>
            </View>
          </View>

          <Pressable
            style={({ pressed }) => [
              styles.closeBtn,
              pressed && styles.closeBtnPressed,
            ]}
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel="Close story modal"
            testID="story-close-button"
          >
            <Text style={styles.closeBtnText}>✕</Text>
          </Pressable>
        </View>

        {/* Tap Gesture Zones: Left (Previous) & Right (Next) */}
        <View style={styles.tapZonesContainer}>
          <Pressable
            style={styles.tapZoneLeft}
            onPress={handlePrevStory}
            accessibilityLabel="Previous story"
          />
          <Pressable
            style={styles.tapZoneRight}
            onPress={handleNextStory}
            accessibilityLabel="Next story"
          />
        </View>

        {/* Center Visual Sound Stage: Avatar + Frequency Waveform */}
        <View style={styles.soundStage} pointerEvents="box-none">
          <View style={styles.stageAvatarWrap}>
            {currentStory.creator?.avatar_url ? (
              <Image
                source={{ uri: currentStory.creator.avatar_url }}
                style={styles.stageAvatar}
              />
            ) : (
              <View style={styles.stageInitial}>
                <Text style={styles.stageInitialText}>{initial}</Text>
              </View>
            )}
          </View>

          <Text style={styles.storyPrompt}>24-Hour Ephemeral Audio</Text>

          {/* Animated Waveform Bars */}
          <View style={styles.waveformRow}>
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
                        outputRange: ['12%', '100%'],
                      }),
                      backgroundColor: hasPassed ? PALETTE.accent : '#3f3f46',
                      opacity: isPlaying ? 1 : 0.45,
                    },
                  ]}
                />
              );
            })}
          </View>

          {/* Timecode and Play/Pause Controls */}
          <View style={styles.timecodeRow}>
            <Text style={styles.timecodeText}>
              {formatDuration(positionSeconds)}
            </Text>
            <Pressable
              style={({ pressed }) => [
                styles.playBtn,
                pressed && styles.playBtnPressed,
              ]}
              onPress={togglePlayPause}
              accessibilityRole="button"
              accessibilityLabel={isPlaying ? 'Pause story' : 'Play story'}
              testID="story-toggle-play"
            >
              {isPlaying ? (
                <PauseMark size={24} color="#ffffff" />
              ) : (
                <PlayMark size={24} color="#ffffff" />
              )}
            </Pressable>
            <Text style={styles.timecodeText}>
              {formatDuration(durationSeconds || currentStory.duration_seconds || 15)}
            </Text>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
    justifyContent: 'space-between',
    paddingTop: 48,
    paddingBottom: 40,
    paddingHorizontal: 16,
  },
  backdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: '#09090b',
  },
  segmentedProgressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    width: '100%',
    marginBottom: 12,
    zIndex: 20,
  },
  segmentTrack: {
    flex: 1,
    height: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  segmentFill: {
    height: '100%',
    backgroundColor: '#ffffff',
    borderRadius: 2,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    zIndex: 20,
    marginBottom: 20,
  },
  creatorInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  avatarRing: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 2,
    borderColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
  },
  avatarImage: {
    width: '100%',
    height: '100%',
  },
  initialFallback: {
    width: '100%',
    height: '100%',
    backgroundColor: PALETTE.card,
    justifyContent: 'center',
    alignItems: 'center',
  },
  initialText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
  },
  nameBlock: {
    flex: 1,
  },
  titleLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  creatorName: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 15,
    color: '#ffffff',
  },
  usernameText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: 'rgba(255, 255, 255, 0.65)',
  },
  expiresText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: '#a1a1aa',
    marginTop: 2,
  },
  closeBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 10,
  },
  closeBtnPressed: {
    opacity: 0.7,
  },
  closeBtnText: {
    color: '#ffffff',
    fontSize: 16,
    fontFamily: 'PlusJakartaSans_600SemiBold',
  },
  tapZonesContainer: {
    ...StyleSheet.absoluteFill,
    flexDirection: 'row',
    zIndex: 10,
  },
  tapZoneLeft: {
    flex: 1,
    height: '100%',
  },
  tapZoneRight: {
    flex: 1,
    height: '100%',
  },
  soundStage: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 15,
    paddingHorizontal: 20,
    gap: 20,
  },
  stageAvatarWrap: {
    width: 120,
    height: 120,
    borderRadius: 60,
    borderWidth: 3,
    borderColor: PALETTE.accent,
    overflow: 'hidden',
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.4,
    shadowRadius: 16,
    elevation: 8,
  },
  stageAvatar: {
    width: '100%',
    height: '100%',
  },
  stageInitial: {
    width: '100%',
    height: '100%',
    backgroundColor: PALETTE.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  stageInitialText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 48,
    color: PALETTE.accent,
  },
  storyPrompt: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 16,
    color: PALETTE.textSecondary,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  waveformRow: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 64,
    gap: 4,
    width: '100%',
    maxWidth: 320,
  },
  waveBar: {
    flex: 1,
    borderRadius: 2,
    minHeight: 4,
  },
  timecodeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 24,
    marginTop: 8,
  },
  timecodeText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#a1a1aa',
    fontVariant: ['tabular-nums'],
  },
  playBtn: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 6,
  },
  playBtnPressed: {
    opacity: 0.8,
  },
});
