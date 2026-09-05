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

  // Device signal state tracked via high-fidelity device signal engine (§5.8)
  const [deviceSignal, setDeviceSignal] = useState<DeviceSignal>(getDeviceSignal(false));

  useEffect(() => {
    const unsubscribe = subscribeDeviceSignal((nextSignal) => {
      setDeviceSignal(nextSignal);
    });
    return unsubscribe;
  }, []);

  // Animated waveform bars
  const bars = useRef(Array.from({ length: 40 }, () => new Animated.Value(0.15))).current;
  const playAnim = useRef<Animated.CompositeAnimation | null>(null);

  // Glow pulse for active card
  const glowAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (isActive) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(glowAnim, { toValue: 1, duration: 1800, useNativeDriver: false }),
          Animated.timing(glowAnim, { toValue: 0, duration: 1800, useNativeDriver: false }),
        ]),
      ).start();
    } else {
      glowAnim.stopAnimation();
      glowAnim.setValue(0);
    }
  }, [isActive, glowAnim]);

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

  useEffect(() => {
    if (isPlaying && item) {
      const anims = bars.map((bar, i) =>
        Animated.loop(
          Animated.sequence([
            Animated.delay(i * 40),
            Animated.timing(bar, {
              toValue: 0.2 + Math.random() * 0.8,
              duration: 300 + Math.random() * 300,
              useNativeDriver: false,
            }),
            Animated.timing(bar, {
              toValue: 0.1 + Math.random() * 0.3,
              duration: 300 + Math.random() * 200,
              useNativeDriver: false,
            }),
          ]),
        ),
      );
      playAnim.current = Animated.parallel(anims);
      playAnim.current.start();

      // Progress animation & telemetry emitter
      let secondsElapsed = 0;
      const interval = setInterval(() => {
        secondsElapsed += 1;
        setProgress((p) => {
          if (p >= 1) {
            setIsPlaying(false);
            return 0;
          }
          const nextP = p + 1 / (item.duration || 1);
          return nextP;
        });

        // Emit telemetry every 3 seconds of active playback with dynamic device signal
        if (secondsElapsed % 3 === 0) {
          const activeSignal = getDeviceSignal(true);
          telemetryApi.recordPlayProgress({
            blipp_id: item.id,
            position_seconds: secondsElapsed,
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
        Animated.timing(b, { toValue: 0.15, duration: 200, useNativeDriver: false }).start();
      });
    }
  }, [isPlaying, bars, item?.duration, item?.id]);

  const [grad1 = PALETTE.accent, grad2 = '#8b5cf6'] = item?.coverGradient ?? [];

  return (
    <View style={[styles.root, { height }]}>
      {/* Background gradient */}
      <View style={[styles.bg, { backgroundColor: grad1 }]} />
      <View style={[StyleSheet.absoluteFill, styles.bgOverlay]} />

      {/* Glow ring on active */}
      {isActive && (
        <Animated.View
          style={[
            styles.glowRing,
            {
              opacity: glowAnim.interpolate({ inputRange: [0, 1], outputRange: [0.0, 0.15] }),
              backgroundColor: grad1,
            },
          ]}
          pointerEvents="none"
        />
      )}

      {/* Content */}
      <View style={styles.content}>
        {/* Header row: Source chip & Sponsored indicator */}
        <View style={styles.headerRow}>
          {item.sourceName && (
            <View style={styles.sourceChip}>
              <Text style={styles.sourceText} numberOfLines={1}>
                {item.sourceName}
              </Text>
            </View>
          )}

          {item.is_sponsored && (
            <View style={styles.sponsoredBadge}>
              <Text style={styles.sponsoredBadgeText}>SPONSORED</Text>
            </View>
          )}
        </View>

        {/* Title */}
        <Text style={styles.title} numberOfLines={3}>{item.title}</Text>

        {/* Author / Sponsor */}
        <View style={styles.authorRow}>
          <Text style={styles.author}>{item.author}</Text>
          {item.sponsor?.tagline && (
            <Text style={styles.sponsorTagline} numberOfLines={1}>
              · {item.sponsor.tagline}
            </Text>
          )}
        </View>

        {/* Waveform */}
        <View style={styles.waveform}>
          {bars.map((bar, i) => (
            <Animated.View
              key={i}
              style={[
                styles.waveBar,
                {
                  height: bar.interpolate({ inputRange: [0, 1], outputRange: ['5%', '100%'] }),
                  backgroundColor: i % 2 === 0 ? grad1 : grad2,
                  opacity: isPlaying
                    ? bar.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] })
                    : 0.3,
                },
              ]}
            />
          ))}
        </View>

        {/* Progress bar */}
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progress * 100}%` }]} />
        </View>

        {/* Controls row */}
        <View style={styles.controls}>
          <Pressable
            style={[styles.playBtn, { backgroundColor: grad1 }]}
            onPress={togglePlay}
            accessibilityRole="button"
            accessibilityLabel={isPlaying ? 'Pause' : 'Play'}
          >
            <Text style={styles.playBtnText}>{isPlaying ? '⏸' : '▶'}</Text>
          </Pressable>

          <View style={styles.meta}>
            <Text style={styles.metaText}>{formatDuration(item.duration)}</Text>
            <Text style={styles.metaDot}>·</Text>
            <Text style={styles.metaText}>{formatListens(item.listenCount)} plays</Text>
          </View>

          <Pressable
            style={styles.likeBtn}
            onPress={onLike}
            accessibilityRole="button"
            accessibilityLabel={item.isLiked ? 'Unlike' : 'Like'}
          >
            <Text style={styles.likeIcon}>{item.isLiked ? '♥' : '♡'}</Text>
            <Text style={styles.likeCount}>{formatListens(item.likeCount)}</Text>
          </Pressable>
        </View>

        {/* Sponsored Call To Action Button */}
        {item.is_sponsored && item.sponsor && (
          <Pressable
            style={styles.ctaButton}
            onPress={() => item.sponsor?.cta_url && Linking.openURL(item.sponsor.cta_url)}
            accessibilityRole="button"
            accessibilityLabel={item.sponsor.cta_text || 'Learn more'}
          >
            <Text style={styles.ctaText}>{item.sponsor.cta_text || 'Learn More'} ↗</Text>
          </Pressable>
        )}

        {/* Tags */}
        {item.tags && item.tags.length > 0 && !item.is_sponsored && (
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
  },
  bg: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.25,
  },
  bgOverlay: {
    backgroundColor: 'rgba(9,9,11,0.75)',
  },
  glowRing: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 0,
  },
  content: {
    flex: 1,
    justifyContent: 'flex-end',
    paddingHorizontal: 24,
    paddingBottom: 80,
    paddingTop: 100,
    gap: 12,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  sourceChip: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  sourceText: {
    fontFamily: 'Inter_500Medium',
    fontSize: 12,
    color: 'rgba(255,255,255,0.8)',
  },
  sponsoredBadge: {
    backgroundColor: 'rgba(245, 158, 11, 0.2)',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.4)',
  },
  sponsoredBadgeText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 11,
    color: '#fbbf24',
    letterSpacing: 0.5,
  },
  title: {
    fontFamily: 'Inter_700Bold',
    fontSize: 24,
    color: '#fff',
    lineHeight: 32,
  },
  authorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  author: {
    fontFamily: 'Inter_500Medium',
    fontSize: 15,
    color: 'rgba(255,255,255,0.65)',
  },
  sponsorTagline: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: 'rgba(255,255,255,0.45)',
    flex: 1,
  },
  // Waveform
  waveform: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    gap: 2.5,
    marginVertical: 4,
  },
  waveBar: {
    flex: 1,
    borderRadius: 2,
    minHeight: 4,
  },
  // Progress
  progressTrack: {
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.15)',
    borderRadius: 2,
  },
  progressFill: {
    height: 3,
    backgroundColor: '#fff',
    borderRadius: 2,
  },
  // Controls
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  playBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
  },
  playBtnText: {
    fontSize: 18,
    color: '#fff',
  },
  meta: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  metaText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: 'rgba(255,255,255,0.6)',
  },
  metaDot: {
    color: 'rgba(255,255,255,0.3)',
  },
  likeBtn: {
    alignItems: 'center',
    gap: 3,
    minWidth: 44,
    minHeight: 44,
    justifyContent: 'center',
  },
  likeIcon: {
    fontSize: 22,
    color: '#fff',
  },
  likeCount: {
    fontFamily: 'Inter_500Medium',
    fontSize: 12,
    color: 'rgba(255,255,255,0.6)',
  },
  ctaButton: {
    backgroundColor: PALETTE.accent,
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  ctaText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 14,
    color: '#fff',
  },
  // Tags
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tag: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  tagText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 12,
    color: 'rgba(255,255,255,0.5)',
  },
});
