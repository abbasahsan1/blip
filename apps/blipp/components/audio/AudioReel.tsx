import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { PALETTE } from '@/lib/palette';
import { telemetryApi } from '@/lib/api';
import { getDeviceSignal, subscribeDeviceSignal } from '@/lib/deviceSignal';
import { PlayMark, PauseMark, HeartMark } from '@/components/common/Icons';
import type { AudioPost, Blipp, DeviceSignal } from '@/lib/types';

function formatDuration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function formatListens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

interface Props {
  post?: AudioPost;
  item?: Blipp;
  isActive: boolean;
  height: number;
  onLike: () => void;
}

export function AudioReel({ post, item: propItem, isActive, height, onLike }: Props) {
  const item = (post || propItem) as Blipp;
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  // Stream source resolved from audio_variants.standard with fallback to canonical audio_url
  const audioSource = item?.audio_variants?.standard || item?.audio_url || item?.audioUrl || '';

  // Device signal state tracked via high-fidelity device signal engine
  const [, setDeviceSignal] = useState<DeviceSignal>(getDeviceSignal(false));

  useEffect(() => {
    const unsubscribe = subscribeDeviceSignal((nextSignal) => {
      setDeviceSignal(nextSignal);
    });
    return unsubscribe;
  }, []);

  // Animated waveform bars: responds strictly to playback state
  const bars = useRef(Array.from({ length: 36 }, () => new Animated.Value(0.2))).current;
  const playAnim = useRef<Animated.CompositeAnimation | null>(null);

  // HTML5 Audio ref for real web stream playback
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof Audio === 'undefined') return;

    if (audioSource) {
      const audio = new Audio(audioSource);
      audioRef.current = audio;

      const handleTimeUpdate = () => {
        if (audio.duration && audio.duration > 0) {
          setProgress(audio.currentTime / audio.duration);
        }
      };
      const handleEnded = () => {
        setIsPlaying(false);
        setProgress(0);
      };
      const handlePause = () => {
        setIsPlaying(false);
      };
      const handlePlay = () => {
        setIsPlaying(true);
      };

      audio.addEventListener('timeupdate', handleTimeUpdate);
      audio.addEventListener('ended', handleEnded);
      audio.addEventListener('pause', handlePause);
      audio.addEventListener('play', handlePlay);

      return () => {
        audio.pause();
        audio.removeEventListener('timeupdate', handleTimeUpdate);
        audio.removeEventListener('ended', handleEnded);
        audio.removeEventListener('pause', handlePause);
        audio.removeEventListener('play', handlePlay);
        audio.src = '';
        audioRef.current = null;
      };
    }
  }, [audioSource]);

  // Pause playback if reel becomes inactive
  useEffect(() => {
    if (!isActive && audioRef.current && isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    }
  }, [isActive, isPlaying]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) {
      setIsPlaying((p) => !p);
      return;
    }

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      audio.play().then(() => {
        setIsPlaying(true);
      }).catch((e) => {
        console.warn('Audio playback error:', e);
        setIsPlaying(true);
      });
    }
  };

  // Waveform animation strictly bound to active playback (functional motion)
  // Progress is driven by audio.timeupdate event — this effect only handles
  // waveform animation and telemetry emission.
  useEffect(() => {
    if (isPlaying && item) {
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

      // Telemetry-only interval — progress is driven by audio.timeupdate
      let secondsElapsed = 0;
      const interval = setInterval(() => {
        secondsElapsed += 1;
        if (secondsElapsed % 3 === 0) {
          const activeSignal = getDeviceSignal(true);
          const audio = audioRef.current;
          const positionSeconds = audio ? Math.floor(audio.currentTime) : secondsElapsed;
          telemetryApi.recordPlayProgress({
            blipp_id: item.id,
            position_seconds: positionSeconds,
            duration_seconds: item.duration,
            device_signal: activeSignal,
          });
        }
      }, 1000);

      return () => {
        clearInterval(interval);
        playAnim.current?.stop();
      };
    } else {
      playAnim.current?.stop();
      bars.forEach((b) => {
        Animated.timing(b, { toValue: 0.2, duration: 180, useNativeDriver: false }).start();
      });
    }
  }, [isPlaying, bars, item?.duration, item?.id]);

  const currentSeconds = Math.floor(progress * (item?.duration || 0));

  return (
    <View style={[styles.root, { height }]}>
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

          {item?.is_sponsored && (
            <View style={styles.sponsoredBadge}>
              <Text style={styles.sponsoredBadgeText}>Sponsored Broadcast</Text>
            </View>
          )}
        </View>

        {/* Blipp Title: Sora Display Typography */}
        <Text style={styles.title} numberOfLines={3}>
          {item?.title}
        </Text>

        {/* Creator Attribution */}
        <View style={styles.authorRow}>
          <Text style={styles.author}>{item?.author}</Text>
          {item?.sponsor?.tagline && (
            <Text style={styles.sponsorTagline} numberOfLines={1}>
              · {item.sponsor.tagline}
            </Text>
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
        <View style={styles.controls}>
          <Pressable
            style={({ pressed }) => [
              styles.playBtn,
              pressed && styles.playBtnPressed,
            ]}
            onPress={togglePlay}
            accessibilityRole="button"
            accessibilityLabel={isPlaying ? 'Pause audio' : 'Play audio'}
          >
            {isPlaying ? (
              <PauseMark size={20} color="#ffffff" />
            ) : (
              <PlayMark size={20} color="#ffffff" />
            )}
          </Pressable>

          <View style={styles.meta}>
            <Text style={styles.timecodeActive}>
              {formatDuration(currentSeconds)}
            </Text>
            <Text style={styles.metaDivider}>/</Text>
            <Text style={styles.timecodeTotal}>
              {formatDuration(item?.duration || 0)}
            </Text>
            <Text style={styles.metaDot}>•</Text>
            <Text style={styles.metaPlays}>
              {formatListens(item?.listenCount || 0)} plays
            </Text>
          </View>

          <Pressable
            style={({ pressed }) => [
              styles.likeBtn,
              pressed && styles.likeBtnPressed,
            ]}
            onPress={onLike}
            accessibilityRole="button"
            accessibilityLabel={item?.isLiked ? 'Unlike audio' : 'Like audio'}
          >
            <HeartMark
              size={20}
              color={item?.isLiked ? PALETTE.accent : PALETTE.textSecondary}
              filled={item?.isLiked}
            />
            <Text
              style={[
                styles.likeCount,
                item?.isLiked && styles.likeCountActive,
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
            onPress={() => item.sponsor?.cta_url && Linking.openURL(item.sponsor.cta_url)}
            accessibilityRole="button"
            accessibilityLabel={item.sponsor.cta_text || 'Learn more'}
          >
            <Text style={styles.ctaText}>{item.sponsor.cta_text || 'Learn More'}</Text>
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
