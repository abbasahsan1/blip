import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { PALETTE } from '@/lib/palette';
import type { AudioPost } from '@/lib/types';

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
  post: AudioPost;
  isActive: boolean;
  height: number;
  onLike: () => void;
}

export function AudioReel({ post, isActive, height, onLike }: Props) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

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

  useEffect(() => {
    if (isPlaying) {
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

      // Fake progress animation (Phase 2 will use real audio position)
      const interval = setInterval(() => {
        setProgress((p) => {
          if (p >= 1) {
            setIsPlaying(false);
            return 0;
          }
          return p + 1 / post.duration;
        });
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
  }, [isPlaying, bars, post.duration]);

  const [grad1 = PALETTE.accent, grad2 = '#8b5cf6'] = post.coverGradient ?? [];

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
        {/* Source chip */}
        {post.sourceName && (
          <View style={styles.sourceChip}>
            <Text style={styles.sourceText} numberOfLines={1}>
              {post.sourceName}
            </Text>
          </View>
        )}

        {/* Title */}
        <Text style={styles.title} numberOfLines={3}>{post.title}</Text>

        {/* Author */}
        <Text style={styles.author}>{post.author}</Text>

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
            onPress={() => setIsPlaying((p) => !p)}
            accessibilityRole="button"
            accessibilityLabel={isPlaying ? 'Pause' : 'Play'}
          >
            <Text style={styles.playBtnText}>{isPlaying ? '⏸' : '▶'}</Text>
          </Pressable>

          <View style={styles.meta}>
            <Text style={styles.metaText}>{formatDuration(post.duration)}</Text>
            <Text style={styles.metaDot}>·</Text>
            <Text style={styles.metaText}>{formatListens(post.listenCount)} plays</Text>
          </View>

          <Pressable
            style={styles.likeBtn}
            onPress={onLike}
            accessibilityRole="button"
            accessibilityLabel={post.isLiked ? 'Unlike' : 'Like'}
          >
            <Text style={styles.likeIcon}>{post.isLiked ? '♥' : '♡'}</Text>
            <Text style={styles.likeCount}>{formatListens(post.likeCount)}</Text>
          </Pressable>
        </View>

        {/* Tags */}
        {post.tags && post.tags.length > 0 && (
          <View style={styles.tags}>
            {post.tags.map((tag) => (
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
  title: {
    fontFamily: 'Inter_700Bold',
    fontSize: 24,
    color: '#fff',
    lineHeight: 32,
  },
  author: {
    fontFamily: 'Inter_500Medium',
    fontSize: 15,
    color: 'rgba(255,255,255,0.65)',
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
