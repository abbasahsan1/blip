import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import { PlayMark, PauseMark, SendMark } from '@/components/common/Icons';
import { useSessionStore } from '@/lib/store/sessionStore';
import { api, resolvePublicAudioUrl } from '@/lib/api';
import type { DMMessageItem } from '@/lib/types';

function formatMessageTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function ConversationScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{
    threadId: string;
    recipientId?: string;
    username?: string;
  }>();

  const threadId = params.threadId;
  const currentUserId = useSessionStore((s) => s.user?.id);

  const [messages, setMessages] = useState<DMMessageItem[]>([]);
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  // Audio preview state for blipp_share cards
  const [playingBlippId, setPlayingBlippId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const loadMessages = useCallback(async () => {
    if (!threadId) return;
    try {
      const res = await api.getThreadMessages(threadId, 40);
      setMessages(res.items || []);
      setNextCursor(res.next_cursor || null);
    } catch {
      setMessages([]);
    }
  }, [threadId]);

  useEffect(() => {
    setIsLoading(true);
    void loadMessages().finally(() => setIsLoading(false));
  }, [loadMessages]);

  const toggleBlippAudio = (blippId: string) => {
    if (playingBlippId === blippId) {
      audioRef.current?.pause();
      setPlayingBlippId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
    }

    if (typeof window === 'undefined' || typeof Audio === 'undefined') return;

    // Resolve public audio URL
    const audioUrl = resolvePublicAudioUrl(`/v1/feed/audio/blipps/${blippId}.m4a`);
    const audio = new Audio(audioUrl);
    audio.play().catch(() => {});
    audio.onended = () => setPlayingBlippId(null);
    audioRef.current = audio;
    setPlayingBlippId(blippId);
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
      }
    };
  }, []);

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text || !threadId || isSending) return;

    setInputText('');
    setIsSending(true);

    // Instant optimistic append
    const tempId = `temp-${Date.now()}`;
    const optimisticMessage: DMMessageItem = {
      message_id: tempId,
      thread_id: threadId,
      sender_id: currentUserId || 'me',
      message_type: 'text',
      body: text,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimisticMessage]);

    try {
      const realMessage = await api.sendMessage(threadId, {
        message_type: 'text',
        body: text,
      });

      setMessages((prev) =>
        prev.map((msg) => (msg.message_id === tempId ? realMessage : msg)),
      );
    } catch {
      // Keep optimistic message or mark error
    } finally {
      setIsSending(false);
    }
  };

  const displayName = params.username
    ? `@${params.username}`
    : params.recipientId
    ? `Creator ${params.recipientId.slice(0, 8)}`
    : 'Conversation';

  const renderMessageBubble = ({ item }: { item: DMMessageItem }) => {
    const isMe = item.sender_id === currentUserId || item.sender_id === 'me';
    const isBlippShare = item.message_type === 'blipp_share';
    const blippId = item.blipp_id || '';
    const isPlayingThis = playingBlippId === blippId;

    return (
      <View
        style={[
          styles.messageRow,
          isMe ? styles.messageRowMe : styles.messageRowThem,
        ]}
      >
        <View
          style={[
            styles.bubble,
            isMe ? styles.bubbleMe : styles.bubbleThem,
            isBlippShare && styles.bubbleShare,
          ]}
        >
          {isBlippShare ? (
            /* Blipp Shared Audio Card */
            <View style={styles.shareCard}>
              <View style={styles.shareHeader}>
                <Text style={styles.shareBadge}>🎵 Audio Reel Shared</Text>
              </View>

              <View style={styles.shareBody}>
                <Pressable
                  style={({ pressed }) => [
                    styles.sharePlayBtn,
                    isPlayingThis && styles.sharePlayBtnActive,
                    pressed && styles.btnPressed,
                  ]}
                  onPress={() => blippId && toggleBlippAudio(blippId)}
                  accessibilityRole="button"
                  accessibilityLabel={isPlayingThis ? 'Pause shared audio' : 'Play shared audio'}
                  testID={`play-share-${blippId}`}
                >
                  {isPlayingThis ? (
                    <PauseMark size={16} color="#ffffff" />
                  ) : (
                    <PlayMark size={16} color="#ffffff" />
                  )}
                </Pressable>

                <View style={styles.shareInfo}>
                  <Text style={styles.shareTitle} numberOfLines={2}>
                    {item.body || 'Shared Blipp Broadcast'}
                  </Text>
                  <Text style={styles.shareHint}>Tap to preview audio</Text>
                </View>
              </View>
            </View>
          ) : (
            /* Standard Text Message */
            <Text style={[styles.messageText, isMe && styles.messageTextMe]}>
              {item.body}
            </Text>
          )}

          <Text style={[styles.messageTime, isMe && styles.messageTimeMe]}>
            {formatMessageTime(item.created_at)}
          </Text>
        </View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={0}
    >
      {/* Conversation Header */}
      <View style={[styles.header, { paddingTop: insets.top + 10 }]}>
        <Pressable
          style={({ pressed }) => [styles.backBtn, pressed && styles.btnPressed]}
          onPress={() => router.back()}
          accessibilityRole="button"
          accessibilityLabel="Back to messages"
        >
          <Text style={styles.backBtnText}>←</Text>
        </Pressable>

        <View style={styles.headerInfo}>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {displayName}
          </Text>
          <View style={styles.statusRow}>
            <View style={styles.onlineDot} />
            <Text style={styles.statusText}>Active frequency</Text>
          </View>
        </View>

        <View style={{ width: 36 }} />
      </View>

      {/* Messages List */}
      <FlatList
        data={messages}
        keyExtractor={(item) => item.message_id}
        renderItem={renderMessageBubble}
        contentContainerStyle={styles.messagesList}
        showsVerticalScrollIndicator={false}
        ListEmptyComponent={
          !isLoading ? (
            <View style={styles.emptyMessages}>
              <Text style={styles.emptyMessagesText}>
                No messages yet. Send a greeting or share a Blipp track!
              </Text>
            </View>
          ) : null
        }
      />

      {/* Input Bar */}
      <View
        style={[
          styles.inputContainer,
          { paddingBottom: Math.max(insets.bottom, 12) },
        ]}
      >
        <TextInput
          style={styles.inputField}
          placeholder="Type a message..."
          placeholderTextColor={PALETTE.textMuted}
          value={inputText}
          onChangeText={setInputText}
          multiline
          maxLength={1000}
          testID="message-input-field"
        />

        <Pressable
          style={({ pressed }) => [
            styles.sendBtn,
            inputText.trim() ? styles.sendBtnActive : styles.sendBtnDisabled,
            pressed && styles.btnPressed,
          ]}
          onPress={handleSend}
          disabled={!inputText.trim() || isSending}
          accessibilityRole="button"
          accessibilityLabel="Send message"
          testID="send-message-button"
        >
          <SendMark
            size={18}
            color={inputText.trim() ? '#ffffff' : PALETTE.textMuted}
          />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
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
    paddingHorizontal: 16,
    paddingBottom: 12,
    backgroundColor: PALETTE.surface,
    borderBottomWidth: 1,
    borderBottomColor: PALETTE.border,
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
  headerInfo: {
    alignItems: 'center',
    flex: 1,
    gap: 2,
  },
  headerTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 16,
    color: PALETTE.text,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  onlineDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#10b981',
  },
  statusText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  btnPressed: {
    opacity: 0.7,
  },
  messagesList: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
  },
  messageRow: {
    flexDirection: 'row',
    width: '100%',
  },
  messageRowMe: {
    justifyContent: 'flex-end',
  },
  messageRowThem: {
    justifyContent: 'flex-start',
  },
  bubble: {
    maxWidth: '80%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
    gap: 4,
  },
  bubbleMe: {
    backgroundColor: PALETTE.accent,
    borderBottomRightRadius: 4,
  },
  bubbleThem: {
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderBottomLeftRadius: 4,
  },
  bubbleShare: {
    padding: 10,
    minWidth: 220,
    backgroundColor: '#18181b',
    borderWidth: 1,
    borderColor: 'rgba(99, 102, 241, 0.4)',
  },
  messageText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.text,
    lineHeight: 20,
  },
  messageTextMe: {
    color: '#ffffff',
  },
  messageTime: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 10,
    color: PALETTE.textMuted,
    alignSelf: 'flex-end',
  },
  messageTimeMe: {
    color: 'rgba(255, 255, 255, 0.7)',
  },
  // Blipp Share Card Inside Bubble
  shareCard: {
    gap: 8,
  },
  shareHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  shareBadge: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 11,
    color: PALETTE.accent,
  },
  shareBody: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: PALETTE.surface,
    padding: 10,
    borderRadius: 8,
  },
  sharePlayBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sharePlayBtnActive: {
    backgroundColor: '#dc2626',
  },
  shareInfo: {
    flex: 1,
    gap: 2,
  },
  shareTitle: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 13,
    color: PALETTE.text,
  },
  shareHint: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  emptyMessages: {
    paddingTop: 80,
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  emptyMessagesText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    textAlign: 'center',
    lineHeight: 20,
  },
  // Input Container
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingTop: 8,
    backgroundColor: PALETTE.surface,
    borderTopWidth: 1,
    borderTopColor: PALETTE.border,
    gap: 10,
  },
  inputField: {
    flex: 1,
    minHeight: 40,
    maxHeight: 100,
    backgroundColor: PALETTE.card,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingHorizontal: 16,
    paddingVertical: 8,
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.text,
  },
  sendBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnActive: {
    backgroundColor: PALETTE.accent,
  },
  sendBtnDisabled: {
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
});
