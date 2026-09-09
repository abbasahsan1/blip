import React, { useCallback, useEffect, useState } from 'react';
import {
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
import { ShareMark } from '@/components/common/Icons';
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

export default function MessagesInboxScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const accessToken = useSessionStore((s) => s.accessToken);
  const currentUserId = useSessionStore((s) => s.user?.id);

  const [threads, setThreads] = useState<DMThreadItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // New Message Modal State
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{
    user_id: string;
    username: string;
    display_name?: string | null;
    avatar_url?: string | null;
  }>>([]);
  const [isSearching, setIsSearching] = useState(false);

  const loadThreads = useCallback(async () => {
    if (!accessToken) {
      setThreads([]);
      return;
    }
    try {
      const data = await api.getThreads(50, 0);
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

  // Load followers / following when New Message modal opens
  const openNewMessageModal = async () => {
    setIsNewModalOpen(true);
    setSearchQuery('');
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

  // Handle Search in modal
  const handleSearch = async (text: string) => {
    setSearchQuery(text);
    const clean = text.trim().replace(/^@/, '');
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
      const profile = await api.getProfileByUsername(clean);
      if (profile && profile.user_id) {
        setSearchResults([
          {
            user_id: profile.user_id,
            username: profile.username,
            display_name: profile.display_name,
            avatar_url: profile.avatar_url,
          },
        ]);
      } else {
        setSearchResults([]);
      }
    } catch {
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelectUser = async (targetUserId: string, username: string) => {
    try {
      const thread = await api.createThread(targetUserId);
      setIsNewModalOpen(false);
      router.push({
        pathname: '/messages/[threadId]' as any,
        params: {
          threadId: thread.thread_id,
          recipientId: targetUserId,
          username,
        },
      });
    } catch {
      // Fallback
    }
  };

  const renderThreadItem = ({ item }: { item: DMThreadItem }) => {
    const otherId = item.participant_ids.find((id) => id !== currentUserId) || item.participant_ids[0];
    const previewText =
      item.latest_message?.message_type === 'blipp_share'
        ? '🎵 Shared a Blipp'
        : item.latest_message?.body || 'Started a conversation';
    const timestamp = formatTimeAgo(item.latest_message?.created_at || item.updated_at || item.created_at);
    const initial = (otherId || 'U').charAt(0).toUpperCase();

    return (
      <Pressable
        style={({ pressed }) => [styles.threadCard, pressed && styles.threadCardPressed]}
        onPress={() => {
          router.push({
            pathname: '/messages/[threadId]' as any,
            params: {
              threadId: item.thread_id,
              recipientId: otherId,
            },
          });
        }}
        accessibilityRole="button"
        accessibilityLabel={`Message thread with ${otherId}`}
        testID={`thread-item-${item.thread_id}`}
      >
        <View style={styles.threadAvatarCircle}>
          <Text style={styles.threadAvatarInitial}>{initial}</Text>
        </View>

        <View style={styles.threadInfo}>
          <View style={styles.threadHeaderRow}>
            <Text style={styles.threadParticipant} numberOfLines={1}>
              {`Creator ${otherId.slice(0, 8)}`}
            </Text>
            <Text style={styles.threadTimestamp}>{timestamp}</Text>
          </View>

          <Text style={styles.threadSnippet} numberOfLines={1}>
            {previewText}
          </Text>
        </View>
      </Pressable>
    );
  };

  if (!accessToken) {
    return (
      <View style={styles.root}>
        <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
          <View style={styles.headerLeft}>
            <Pressable
              style={({ pressed }) => [styles.backBtn, pressed && styles.btnPressed]}
              onPress={() => router.back()}
              accessibilityRole="button"
              accessibilityLabel="Back"
            >
              <Text style={styles.backBtnText}>←</Text>
            </Pressable>
            <Text style={styles.headerTitle}>Messages</Text>
          </View>
        </View>

        <View style={styles.authGuardContainer}>
          <View style={styles.authGuardIconWrap}>
            <ShareMark size={40} color={PALETTE.accent} />
          </View>
          <Text style={styles.authGuardTitle}>Sign in to view your conversations</Text>
          <Text style={styles.authGuardSub}>
            Connect with creators, discuss audio stories, and share Blipps in private threads.
          </Text>
          <Pressable
            style={({ pressed }) => [styles.authGuardBtn, pressed && styles.btnPressed]}
            onPress={() => router.push('/(auth)/sign-in' as any)}
            accessibilityRole="button"
            accessibilityLabel="Sign in"
            testID="messages-signin-button"
          >
            <Text style={styles.authGuardBtnText}>Sign In</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {/* Studio Header Bar */}
      <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
        <View style={styles.headerLeft}>
          <Pressable
            style={({ pressed }) => [styles.backBtn, pressed && styles.btnPressed]}
            onPress={() => router.back()}
            accessibilityRole="button"
            accessibilityLabel="Back"
          >
            <Text style={styles.backBtnText}>←</Text>
          </Pressable>
          <Text style={styles.headerTitle}>Messages</Text>
        </View>

        <Pressable
          style={({ pressed }) => [styles.newBtn, pressed && styles.btnPressed]}
          onPress={openNewMessageModal}
          accessibilityRole="button"
          accessibilityLabel="New direct message"
          testID="new-message-button"
        >
          <Text style={styles.newBtnText}>+ New</Text>
        </Pressable>
      </View>

      {/* Threads List */}
      <FlatList
        data={threads}
        keyExtractor={(item) => item.thread_id}
        renderItem={renderThreadItem}
        contentContainerStyle={[
          styles.listContent,
          threads.length === 0 && styles.listContentEmpty,
        ]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={onRefresh}
            tintColor={PALETTE.accent}
            colors={[PALETTE.accent]}
          />
        }
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyContainer} testID="inbox-empty-state">
              <View style={styles.emptyIconWrap}>
                <ShareMark size={32} color={PALETTE.textMuted} />
              </View>
              <Text style={styles.emptyTitle}>No messages yet</Text>
              <Text style={styles.emptySub}>
                Exchange direct messages with creators and share audio broadcasts.
              </Text>
              <Pressable
                style={({ pressed }) => [styles.emptyActionBtn, pressed && styles.btnPressed]}
                onPress={openNewMessageModal}
              >
                <Text style={styles.emptyActionBtnText}>Start a Conversation</Text>
              </Pressable>
            </View>
          ) : null
        }
      />

      {/* New Message Search Modal */}
      <Modal
        visible={isNewModalOpen}
        animationType="slide"
        transparent
        onRequestClose={() => setIsNewModalOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalSheet, { paddingTop: insets.top + 16 }]}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>New Conversation</Text>
              <Pressable
                style={({ pressed }) => [styles.modalCloseBtn, pressed && styles.btnPressed]}
                onPress={() => setIsNewModalOpen(false)}
              >
                <Text style={styles.modalCloseText}>✕</Text>
              </Pressable>
            </View>

            {/* Search Input */}
            <View style={styles.searchBar}>
              <TextInput
                style={styles.searchInput}
                placeholder="Search by @username..."
                placeholderTextColor={PALETTE.textMuted}
                value={searchQuery}
                onChangeText={handleSearch}
                autoCapitalize="none"
                autoCorrect={false}
                autoFocus
              />
            </View>

            {/* Search Results */}
            <FlatList
              data={searchResults}
              keyExtractor={(item) => item.user_id}
              contentContainerStyle={styles.searchList}
              renderItem={({ item }) => (
                <Pressable
                  style={({ pressed }) => [styles.userCard, pressed && styles.userCardPressed]}
                  onPress={() => handleSelectUser(item.user_id, item.username)}
                  accessibilityRole="button"
                  accessibilityLabel={`Message ${item.username}`}
                >
                  <View style={styles.userAvatar}>
                    <Text style={styles.userAvatarInitial}>
                      {(item.display_name || item.username).charAt(0).toUpperCase()}
                    </Text>
                  </View>
                  <View style={styles.userInfo}>
                    <Text style={styles.userDisplayName}>
                      {item.display_name || item.username}
                    </Text>
                    <Text style={styles.userHandle}>@{item.username}</Text>
                  </View>
                  <Text style={styles.userArrow}>→</Text>
                </Pressable>
              )}
              ListEmptyComponent={
                !isSearching ? (
                  <View style={styles.noResults}>
                    <Text style={styles.noResultsText}>
                      {searchQuery
                        ? `No profile found for "${searchQuery}"`
                        : 'Type a creator username to start chatting.'}
                    </Text>
                  </View>
                ) : null
              }
            />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingBottom: 12,
    backgroundColor: PALETTE.surface,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  backBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    backgroundColor: PALETTE.card,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  backBtnText: {
    color: PALETTE.text,
    fontSize: 18,
    fontWeight: 'bold',
  },
  headerTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    letterSpacing: -0.5,
  },
  newBtn: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    backgroundColor: PALETTE.accent,
    borderRadius: 8,
  },
  newBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: '#ffffff',
  },
  btnPressed: {
    opacity: 0.7,
  },
  listContent: {
    padding: 16,
    gap: 10,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
  },
  listContentEmpty: {
    flexGrow: 1,
    justifyContent: 'center',
  },
  threadCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    backgroundColor: PALETTE.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
    gap: 12,
  },
  threadCardPressed: {
    backgroundColor: PALETTE.cardHover,
    borderColor: PALETTE.accent,
  },
  threadAvatarCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#1e1b4b',
    borderWidth: 1.5,
    borderColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  threadAvatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 16,
    color: '#ffffff',
  },
  threadInfo: {
    flex: 1,
    gap: 4,
  },
  threadHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  threadParticipant: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: PALETTE.text,
    flex: 1,
  },
  threadTimestamp: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  threadSnippet: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
  },
  // Empty Inbox State
  emptyContainer: {
    alignItems: 'center',
    paddingHorizontal: 32,
    gap: 12,
  },
  emptyIconWrap: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
  },
  emptySub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 280,
  },
  emptyActionBtn: {
    marginTop: 6,
    paddingHorizontal: 18,
    paddingVertical: 10,
    backgroundColor: PALETTE.accent,
    borderRadius: 8,
  },
  emptyActionBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#ffffff',
  },
  // New Message Modal
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(9, 9, 11, 0.85)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: PALETTE.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderWidth: 1,
    borderColor: PALETTE.border,
    maxHeight: '85%',
    minHeight: '60%',
    paddingHorizontal: 20,
    paddingBottom: 24,
    gap: 14,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
  },
  modalCloseBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: PALETTE.card,
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalCloseText: {
    fontSize: 14,
    color: PALETTE.textMuted,
  },
  searchBar: {
    backgroundColor: PALETTE.card,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  searchInput: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.text,
  },
  searchList: {
    gap: 8,
    paddingTop: 8,
  },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    gap: 12,
  },
  userCardPressed: {
    backgroundColor: PALETTE.cardHover,
  },
  userAvatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#312e81',
    justifyContent: 'center',
    alignItems: 'center',
  },
  userAvatarInitial: {
    fontFamily: 'Sora_700Bold',
    fontSize: 15,
    color: '#ffffff',
  },
  userInfo: {
    flex: 1,
    gap: 2,
  },
  userDisplayName: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  userHandle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  userArrow: {
    fontSize: 16,
    color: PALETTE.textMuted,
  },
  noResults: {
    padding: 24,
    alignItems: 'center',
  },
  noResultsText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    textAlign: 'center',
  },
  // Auth Guard
  authGuardContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
    gap: 12,
  },
  authGuardIconWrap: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  authGuardTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 20,
    color: PALETTE.text,
    textAlign: 'center',
  },
  authGuardSub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
    maxWidth: 290,
    marginBottom: 12,
  },
  authGuardBtn: {
    backgroundColor: PALETTE.accent,
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 160,
  },
  authGuardBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: '#ffffff',
  },
});
