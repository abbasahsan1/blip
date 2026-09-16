import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import {
  ShareMark,
  PlusMark,
  StatusCheckMark,
} from '@/components/common/Icons';
import { useSessionStore } from '@/lib/store/sessionStore';
import { api } from '@/lib/api';
import type { DMThreadItem } from '@/lib/types';

function formatTimeAgo(isoString?: string | null): string {
  if (!isoString) return '';
  try {
    const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return '';
  }
}

export default function VibesTabScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const accessToken = useSessionStore((s) => s.accessToken);
  const currentUserId = useSessionStore((s) => s.user?.id);

  const [threads, setThreads] = useState<DMThreadItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // New Chat Search Modal State
  const [isNewChatOpen, setIsNewChatOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{
    user_id: string;
    username: string;
    display_name?: string | null;
    avatar_url?: string | null;
  }>>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isStartingChat, setIsStartingChat] = useState(false);

  const loadThreads = useCallback(async () => {
    if (!accessToken) {
      setThreads([]);
      return;
    }
    try {
      const data = await api.getDMThreads(50, 0);
      setThreads(data || []);
    } catch {
      setThreads([]);
    }
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      setIsLoading(false);
      setThreads([]);
      return;
    }
    setIsLoading(true);
    void loadThreads().finally(() => setIsLoading(false));
  }, [accessToken, loadThreads]);

  const onRefresh = async () => {
    if (!accessToken) return;
    setIsRefreshing(true);
    await loadThreads();
    setIsRefreshing(false);
  };

  // Open "New Chat" search sheet
  const openNewChatModal = async () => {
    setIsNewChatOpen(true);
    setSearchQuery('');
    setSearchResults([]);
    if (currentUserId) {
      setIsSearching(true);
      try {
        const res = await api.getUserFollowing(currentUserId);
        setSearchResults(res.items || []);
      } catch {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }
  };

  // Search profiles via api.searchProfiles
  const handleSearch = async (text: string) => {
    setSearchQuery(text);
    const clean = text.trim();
    if (!clean) {
      if (currentUserId) {
        try {
          const res = await api.getUserFollowing(currentUserId);
          setSearchResults(res.items || []);
        } catch {
          setSearchResults([]);
        }
      }
      return;
    }

    setIsSearching(true);
    try {
      const profiles = await api.searchProfiles(clean);
      setSearchResults(profiles || []);
    } catch {
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // Start chat with user
  const handleSelectUser = async (targetUserId: string) => {
    if (isStartingChat) return;
    setIsStartingChat(true);
    try {
      const thread = await api.createThread(targetUserId);
      setIsNewChatOpen(false);
      router.push(`/messages/${thread.thread_id}` as any);
    } catch {
      // Navigate on fallback
    } finally {
      setIsStartingChat(false);
    }
  };

  const renderThreadItem = ({ item }: { item: DMThreadItem }) => {
    const participant = item.other_participant;
    const displayName = participant?.display_name || participant?.username || 'Creator';
    const username = participant?.username || 'user';
    const latestMsg = item.latest_message;
    const hasUnread = Boolean((item as any).unread_count && (item as any).unread_count > 0);
    const lastSnippet = latestMsg?.message_type === 'blipp_share'
      ? '🎵 Shared a Blipp broadcast'
      : latestMsg?.body || 'No messages yet';
    const timestamp = formatTimeAgo(latestMsg?.created_at || item.created_at);

    return (
      <Pressable
        style={({ pressed }) => [
          styles.threadCard,
          pressed && styles.threadCardPressed,
        ]}
        onPress={() => router.push(`/messages/${item.thread_id}` as any)}
        accessibilityRole="button"
        accessibilityLabel={`Chat with ${displayName}`}
        testID={`thread-item-${item.thread_id}`}
      >
        <View style={styles.avatarWrapper}>
          <View style={styles.avatarCircle}>
            <Text style={styles.avatarInitial}>
              {displayName.charAt(0).toUpperCase()}
            </Text>
          </View>
          {/* Unread / Active Status Glow Dot */}
          {hasUnread ? (
            <View style={styles.unreadGlowDot} />
          ) : (
            <View style={styles.onlineStatusDot} />
          )}
        </View>

        <View style={styles.threadContent}>
          <View style={styles.threadHeaderRow}>
            <Text style={styles.displayNameText} numberOfLines={1}>
              {displayName}
            </Text>
            <Text style={styles.timestampText}>{timestamp}</Text>
          </View>

          <Text style={styles.handleText} numberOfLines={1}>
            @{username}
          </Text>

          <Text
            style={[
              styles.lastMessageText,
              hasUnread && styles.lastMessageUnread,
            ]}
            numberOfLines={1}
          >
            {lastSnippet}
          </Text>
        </View>
      </Pressable>
    );
  };

  if (!accessToken) {
    return (
      <View style={styles.root}>
        <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
          <Text style={styles.headerTitle}>Vibes 💬</Text>
          <Text style={styles.headerSubtitle}>
            Direct frequencies, voice notes & conversation threads
          </Text>
        </View>
        <View style={styles.authGuardContainer}>
          <View style={styles.authGuardIconCircle}>
            <ShareMark size={42} color={PALETTE.accent} />
          </View>
          <Text style={styles.authGuardHeading}>Sign in to access your Vibes</Text>
          <Text style={styles.authGuardSubtext}>
            Connect directly with creators, echo audio broadcasts, and exchange private messages.
          </Text>
          <Pressable
            style={({ pressed }) => [
              styles.authGuardBtn,
              pressed && styles.authGuardBtnPressed,
            ]}
            onPress={() => router.push('/(auth)/sign-in' as any)}
            accessibilityRole="button"
            accessibilityLabel="Sign in to view messages"
            testID="vibes-signin-button"
          >
            <Text style={styles.authGuardBtnText}>Sign In to Blipp</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <View style={styles.headerTitleRow}>
          <Text style={styles.headerTitle}>Vibes 💬</Text>
          {threads.length > 0 && (
            <View style={styles.threadCountBadge}>
              <Text style={styles.threadCountText}>{threads.length}</Text>
            </View>
          )}
        </View>
        <Text style={styles.headerSubtitle}>
          Direct frequencies, voice notes & conversation threads
        </Text>
      </View>

      {/* Conversations List */}
      {isLoading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={PALETTE.accent} />
          <Text style={styles.loadingText}>Tuning into your conversations...</Text>
        </View>
      ) : threads.length === 0 ? (
        <View style={styles.emptyContainer}>
          <View style={styles.emptyIconCircle}>
            <ShareMark size={44} color={PALETTE.textMuted} />
          </View>
          <Text style={styles.emptyHeading}>No Vibes Yet</Text>
          <Text style={styles.emptySubheading}>
            Echo a Blipp from your feed or start a new conversation with creators below.
          </Text>
          <Pressable style={styles.emptyActionBtn} onPress={openNewChatModal}>
            <Text style={styles.emptyActionText}>Start New Chat</Text>
          </Pressable>
        </View>
      ) : (
        <FlatList
          data={threads}
          keyExtractor={(item) => item.thread_id}
          renderItem={renderThreadItem}
          contentContainerStyle={[
            styles.listContent,
            { paddingBottom: insets.bottom + 90 },
          ]}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={onRefresh}
              tintColor={PALETTE.accent}
              colors={[PALETTE.accent]}
            />
          }
        />
      )}

      {/* Floating Action Button: New Chat */}
      <Pressable
        style={({ pressed }) => [
          styles.fabBtn,
          { bottom: insets.bottom + 80 },
          pressed && styles.fabBtnPressed,
        ]}
        onPress={openNewChatModal}
        accessibilityRole="button"
        accessibilityLabel="Start new chat"
        testID="new-chat-fab"
      >
        <PlusMark size={22} color="#FFFFFF" />
        <Text style={styles.fabText}>New Chat</Text>
      </Pressable>

      {/* New Chat Search Sheet Modal */}
      <Modal
        visible={isNewChatOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setIsNewChatOpen(false)}
      >
        <Pressable
          style={styles.modalOverlay}
          onPress={() => setIsNewChatOpen(false)}
        >
          <Pressable style={styles.modalContent} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalHeading}>Start Conversation</Text>
            <Text style={styles.modalSubheading}>
              Find creators and listeners by handle or username
            </Text>

            {/* Search Input */}
            <View style={styles.searchBarWrapper}>
              <TextInput
                style={styles.searchInput}
                placeholder="Search @username..."
                placeholderTextColor={PALETTE.textMuted}
                value={searchQuery}
                onChangeText={handleSearch}
                autoCapitalize="none"
                autoCorrect={false}
                autoFocus
              />
            </View>

            {isSearching ? (
              <View style={styles.searchLoading}>
                <ActivityIndicator size="small" color={PALETTE.accent} />
              </View>
            ) : searchResults.length === 0 ? (
              <View style={styles.searchEmpty}>
                <Text style={styles.searchEmptyText}>
                  {searchQuery ? 'No creators found matching that handle' : 'Type a handle above to search'}
                </Text>
              </View>
            ) : (
              <FlatList
                data={searchResults}
                keyExtractor={(u) => u.user_id}
                style={styles.resultsList}
                renderItem={({ item: user }) => (
                  <Pressable
                    style={({ pressed }) => [
                      styles.userResultRow,
                      pressed && styles.userResultRowPressed,
                    ]}
                    onPress={() => handleSelectUser(user.user_id)}
                    disabled={isStartingChat}
                  >
                    <View style={styles.resultAvatarCircle}>
                      <Text style={styles.resultAvatarInitial}>
                        {(user.display_name || user.username || 'U').charAt(0).toUpperCase()}
                      </Text>
                    </View>
                    <View style={styles.resultInfo}>
                      <Text style={styles.resultDisplayName}>
                        {user.display_name || user.username}
                      </Text>
                      <Text style={styles.resultHandle}>@{user.username}</Text>
                    </View>
                    <View style={styles.chatActionChip}>
                      <Text style={styles.chatActionChipText}>Chat</Text>
                    </View>
                  </Pressable>
                )}
              />
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
    backgroundColor: PALETTE.bg,
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 16,
    backgroundColor: PALETTE.surface,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  headerTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 4,
  },
  headerTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 24,
    color: PALETTE.primary,
    letterSpacing: -0.5,
  },
  threadCountBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
    backgroundColor: PALETTE.accentDim,
    borderWidth: 1,
    borderColor: PALETTE.accent,
  },
  threadCountText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: PALETTE.accent,
  },
  headerSubtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },

  // Thread Cards
  listContent: {
    padding: 16,
    gap: 12,
  },
  threadCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    backgroundColor: PALETTE.card,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: PALETTE.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 8,
    elevation: 3,
  },
  threadCardPressed: {
    backgroundColor: PALETTE.cardHover,
    transform: [{ scale: 0.99 }],
  },
  avatarWrapper: {
    position: 'relative',
    marginRight: 14,
  },
  avatarCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: PALETTE.borderGlass,
  },
  avatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: '#FFFFFF',
  },
  unreadGlowDot: {
    position: 'absolute',
    right: 0,
    top: 0,
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: PALETTE.magenta,
    borderWidth: 2,
    borderColor: PALETTE.card,
    shadowColor: PALETTE.magenta,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 6,
  },
  onlineStatusDot: {
    position: 'absolute',
    right: 1,
    bottom: 1,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: PALETTE.lime,
    borderWidth: 2,
    borderColor: PALETTE.card,
  },
  threadContent: {
    flex: 1,
  },
  threadHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 2,
  },
  displayNameText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 15,
    color: PALETTE.primary,
    flex: 1,
    marginRight: 8,
  },
  timestampText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  handleText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textSecondary,
    marginBottom: 4,
  },
  lastMessageText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },
  lastMessageUnread: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    color: PALETTE.primary,
  },

  // Floating Action Button
  fabBtn: {
    position: 'absolute',
    right: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 28,
    backgroundColor: PALETTE.accent,
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.7,
    shadowRadius: 12,
    elevation: 8,
    borderWidth: 1.5,
    borderColor: 'rgba(255, 255, 255, 0.2)',
  },
  fabBtnPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.96 }],
  },
  fabText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#FFFFFF',
  },

  // Search Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.78)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: PALETTE.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingTop: 12,
    paddingBottom: 40,
    paddingHorizontal: 20,
    maxHeight: '75%',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  modalHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.border,
    alignSelf: 'center',
    marginBottom: 16,
  },
  modalHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.primary,
    marginBottom: 4,
  },
  modalSubheading: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    marginBottom: 16,
  },
  searchBarWrapper: {
    backgroundColor: PALETTE.card,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: PALETTE.border,
    marginBottom: 14,
  },
  searchInput: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: PALETTE.primary,
  },
  searchLoading: {
    paddingVertical: 24,
    alignItems: 'center',
  },
  searchEmpty: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  searchEmptyText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    textAlign: 'center',
  },
  resultsList: {
    marginTop: 4,
  },
  userResultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.borderSubtle,
  },
  userResultRowPressed: {
    backgroundColor: PALETTE.cardHover,
  },
  resultAvatarCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  resultAvatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 16,
    color: '#FFFFFF',
  },
  resultInfo: {
    flex: 1,
  },
  resultDisplayName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.primary,
  },
  resultHandle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textSecondary,
  },
  chatActionChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 14,
    backgroundColor: PALETTE.accent,
  },
  chatActionChipText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: '#FFFFFF',
  },

  // Auth Guard
  authGuardContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  authGuardIconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: PALETTE.accentDim,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
    borderWidth: 1,
    borderColor: PALETTE.accent,
  },
  authGuardHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 20,
    color: PALETTE.primary,
    marginBottom: 8,
    textAlign: 'center',
  },
  authGuardSubtext: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 24,
  },
  authGuardBtn: {
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 24,
    backgroundColor: PALETTE.accent,
  },
  authGuardBtnPressed: {
    opacity: 0.8,
  },
  authGuardBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: '#FFFFFF',
  },

  // Center / Empty Loading
  centerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  loadingText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    marginTop: 12,
  },
  emptyContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  emptyIconCircle: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: PALETTE.surface,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  emptyHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 19,
    color: PALETTE.primary,
    marginBottom: 8,
  },
  emptySubheading: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 19,
    marginBottom: 20,
  },
  emptyActionBtn: {
    paddingHorizontal: 22,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: PALETTE.accent,
  },
  emptyActionText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: '#FFFFFF',
  },
});
