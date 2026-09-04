import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useSessionStore } from '@/lib/store/sessionStore';
import { useFeedStore } from '@/lib/store/feedStore';
import { PALETTE } from '@/lib/palette';

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const user = useSessionStore((s) => s.user);
  const signOut = useSessionStore((s) => s.signOut);
  const posts = useFeedStore((s) => s.posts);

  const initials = (user?.displayName ?? user?.username ?? '?')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={[
        styles.scroll,
        { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 },
      ]}
      showsVerticalScrollIndicator={false}
    >
      {/* Avatar */}
      <View style={styles.avatarWrap}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
        <View style={styles.avatarGlow} pointerEvents="none" />
      </View>

      {/* Name */}
      <Text style={styles.displayName}>
        {user?.displayName ?? user?.username ?? 'Listener'}
      </Text>
      <Text style={styles.handle}>@{user?.username ?? 'you'}</Text>
      <Text style={styles.email}>{user?.email ?? ''}</Text>

      {/* Stats */}
      <View style={styles.statsRow}>
        <Stat label="Blipps" value={String(posts.length)} />
        <View style={styles.statDivider} />
        <Stat label="Listening" value="0h" />
        <View style={styles.statDivider} />
        <Stat label="Liked" value="0" />
      </View>

      {/* Account section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Account</Text>
        <View style={styles.sectionCard}>
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Email</Text>
            <Text style={styles.rowValue} numberOfLines={1}>{user?.email ?? '—'}</Text>
          </View>
          <View style={[styles.row, { borderTopWidth: 1, borderTopColor: PALETTE.border }]}>
            <Text style={styles.rowLabel}>Username</Text>
            <Text style={styles.rowValue}>@{user?.username ?? '—'}</Text>
          </View>
        </View>
      </View>

      {/* Sign out */}
      <Pressable
        id="profile-sign-out"
        style={({ pressed }) => [styles.signOut, pressed && styles.signOutPressed]}
        onPress={() => void signOut()}
        accessibilityRole="button"
        accessibilityLabel="Sign out"
      >
        <Text style={styles.signOutText}>Sign out</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  scroll: {
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  // Avatar
  avatarWrap: {
    position: 'relative',
    marginBottom: 16,
  },
  avatar: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: PALETTE.accentDim,
  },
  avatarGlow: {
    position: 'absolute',
    inset: -8,
    borderRadius: 52,
    backgroundColor: PALETTE.accentDim,
    zIndex: -1,
  },
  avatarText: {
    fontFamily: 'Inter_700Bold',
    fontSize: 32,
    color: '#fff',
  },
  // Names
  displayName: {
    fontFamily: 'Inter_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    marginBottom: 2,
  },
  handle: {
    fontFamily: 'Inter_500Medium',
    fontSize: 14,
    color: PALETTE.accent,
  },
  email: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    marginTop: 4,
  },
  // Stats
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: PALETTE.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingVertical: 16,
    paddingHorizontal: 24,
    gap: 16,
    marginTop: 24,
    alignSelf: 'stretch',
  },
  stat: {
    flex: 1,
    alignItems: 'center',
    gap: 4,
  },
  statValue: {
    fontFamily: 'Inter_700Bold',
    fontSize: 20,
    color: PALETTE.text,
  },
  statLabel: {
    fontFamily: 'Inter_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
  },
  statDivider: {
    width: 1,
    height: 32,
    backgroundColor: PALETTE.border,
  },
  // Section
  section: {
    alignSelf: 'stretch',
    marginTop: 28,
    gap: 10,
  },
  sectionTitle: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 13,
    color: PALETTE.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  sectionCard: {
    backgroundColor: PALETTE.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
    gap: 12,
  },
  rowLabel: {
    fontFamily: 'Inter_500Medium',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  rowValue: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
    flex: 1,
    textAlign: 'right',
  },
  // Sign out
  signOut: {
    marginTop: 32,
    alignSelf: 'stretch',
    borderWidth: 1,
    borderColor: `${PALETTE.error}40`,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    backgroundColor: PALETTE.errorDim,
    minHeight: 52,
    justifyContent: 'center',
  },
  signOutPressed: {
    opacity: 0.7,
  },
  signOutText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 15,
    color: PALETTE.error,
  },
});
