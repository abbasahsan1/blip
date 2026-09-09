/**
 * StoriesTray
 *
 * Ephemeral 24-hour audio stories reel (§5.4).
 * Features:
 *   - "Your Story (+)" quick-action avatar for recording stories up to 60s
 *   - Live feed of creator story avatars with gradient/accent ring
 *   - Tap to launch full-screen StoryModal with expo-av audio playback
 *   - Tap "Your Story (+)" to launch StoryRecordingSheet
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { PALETTE } from '@/lib/palette';
import { PlusMark } from '@/components/common/Icons';
import { api } from '@/lib/api';
import { useSessionStore } from '@/lib/store/sessionStore';
import { StoryModal } from './StoryModal';
import { StoryRecordingSheet } from './StoryRecordingSheet';
import type { StoryItem } from '@/lib/types';

export function StoriesTray() {
  const user = useSessionStore((s) => s.user);

  const [stories, setStories] = useState<StoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Full-screen StoryModal state
  const [selectedStoryIndex, setSelectedStoryIndex] = useState(0);
  const [isStoryModalOpen, setIsStoryModalOpen] = useState(false);

  // Story recording sheet state
  const [isRecordSheetOpen, setIsRecordSheetOpen] = useState(false);

  const fetchStories = useCallback(async () => {
    setIsLoading(true);
    try {
      const items = await api.getStories();
      setStories(items || []);
    } catch {
      setStories([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStories();
  }, [fetchStories]);

  const handleOpenStory = (index: number) => {
    setSelectedStoryIndex(index);
    setIsStoryModalOpen(true);
  };

  const currentUserInitial = (
    user?.displayName ||
    user?.username ||
    'You'
  )
    .charAt(0)
    .toUpperCase();

  return (
    <View style={styles.container} testID="stories-tray">
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {/* 1. "Your Story (+)" Action Avatar */}
        <Pressable
          style={styles.avatarCard}
          onPress={() => setIsRecordSheetOpen(true)}
          accessibilityRole="button"
          accessibilityLabel="Record new 24h story"
          testID="your-story-record-trigger"
        >
          <View style={styles.yourStoryRing}>
            <View style={styles.avatarInner}>
              {user?.avatarUrl ? (
                <Image
                  source={{ uri: user.avatarUrl }}
                  style={styles.avatarImage}
                />
              ) : (
                <View style={styles.yourStoryInitial}>
                  <Text style={styles.yourStoryInitialText}>
                    {currentUserInitial}
                  </Text>
                </View>
              )}
            </View>

            {/* Tactile (+) Badge Overlay */}
            <View style={styles.plusBadge}>
              <PlusMark size={12} color="#ffffff" />
            </View>
          </View>

          <Text style={styles.creatorLabel} numberOfLines={1}>
            Your Story
          </Text>
        </Pressable>

        {/* 2. Active Stories from Followed Creators */}
        {stories.map((story, index) => {
          const creatorName =
            story.creator?.display_name ||
            story.creator?.username ||
            `Creator ${story.creator_id.slice(0, 6)}`;
          const initial = creatorName.charAt(0).toUpperCase();

          return (
            <Pressable
              key={story.story_id}
              style={styles.avatarCard}
              onPress={() => handleOpenStory(index)}
              accessibilityRole="button"
              accessibilityLabel={`Play story by ${creatorName}`}
              testID={`story-avatar-${story.story_id}`}
            >
              {/* Circular avatar with accent ring */}
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

      {/* Full-Screen Ephemeral Story Viewer */}
      <StoryModal
        stories={stories}
        initialIndex={selectedStoryIndex}
        visible={isStoryModalOpen}
        onClose={() => setIsStoryModalOpen(false)}
      />

      {/* Quick Audio Story Recording Sheet */}
      <StoryRecordingSheet
        visible={isRecordSheetOpen}
        onClose={() => setIsRecordSheetOpen(false)}
        onStoryUploaded={() => {
          void fetchStories();
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 6,
    backgroundColor: 'transparent',
  },
  scrollContent: {
    paddingHorizontal: 16,
    gap: 14,
    alignItems: 'center',
  },
  avatarCard: {
    alignItems: 'center',
    width: 64,
    gap: 5,
  },
  yourStoryRing: {
    width: 58,
    height: 58,
    borderRadius: 29,
    borderWidth: 1.5,
    borderColor: PALETTE.border,
    padding: 2,
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
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
  },
  avatarInner: {
    width: '100%',
    height: '100%',
    borderRadius: 26,
    overflow: 'hidden',
    backgroundColor: PALETTE.card,
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
    backgroundColor: PALETTE.surface,
  },
  initialText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
  },
  yourStoryInitial: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: PALETTE.card,
  },
  yourStoryInitialText: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 17,
    color: PALETTE.textSecondary,
  },
  plusBadge: {
    position: 'absolute',
    bottom: -1,
    right: -1,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: PALETTE.bg,
  },
  creatorLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    width: 64,
  },
});
