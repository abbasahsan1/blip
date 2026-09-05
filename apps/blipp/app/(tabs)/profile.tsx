import { useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
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

  const [legalModal, setLegalModal] = useState<'terms' | 'privacy' | null>(null);

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
        { paddingTop: insets.top + 32, paddingBottom: insets.bottom + 36 },
      ]}
      showsVerticalScrollIndicator={false}
    >
      {/* Operator Avatar: Solid tactile bezel, no radial glow orb */}
      <View style={styles.avatarChassis}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
      </View>

      {/* Operator Identity */}
      <Text style={styles.displayName}>
        {user?.displayName ?? user?.username ?? 'Operator'}
      </Text>
      <Text style={styles.handle}>@{user?.username ?? 'account'}</Text>
      {user?.email && <Text style={styles.email}>{user.email}</Text>}

      {/* Acoustic Console Stats */}
      <View style={styles.statsRow}>
        <Stat label="Broadcasts" value={String(posts.length)} />
        <View style={styles.statDivider} />
        <Stat label="Airtime" value="0h" />
        <View style={styles.statDivider} />
        <Stat label="Reactions" value="0" />
      </View>

      {/* Account Parameters Section */}
      <View style={styles.section}>
        <Text style={styles.sectionHeading}>Account Parameters</Text>
        <View style={styles.sectionCard}>
          <View style={styles.row}>
            <Text style={styles.rowLabel}>Email Address</Text>
            <Text style={styles.rowValue} numberOfLines={1}>
              {user?.email || 'Not specified'}
            </Text>
          </View>
          <View style={[styles.row, styles.rowBorder]}>
            <Text style={styles.rowLabel}>Operator Handle</Text>
            <Text style={styles.rowValue}>
              @{user?.username || 'unassigned'}
            </Text>
          </View>
        </View>
      </View>

      {/* Legal & Compliance Section (Required Surface) */}
      <View style={styles.section}>
        <Text style={styles.sectionHeading}>Legal & Compliance</Text>
        <View style={styles.sectionCard}>
          <Pressable
            style={styles.legalRow}
            onPress={() => setLegalModal('terms')}
            accessibilityRole="button"
            accessibilityLabel="Terms of Service"
          >
            <Text style={styles.legalLabel}>Terms of Service</Text>
            <Text style={styles.legalAction}>View</Text>
          </Pressable>
          <Pressable
            style={[styles.legalRow, styles.rowBorder]}
            onPress={() => setLegalModal('privacy')}
            accessibilityRole="button"
            accessibilityLabel="Privacy Policy"
          >
            <Text style={styles.legalLabel}>Privacy Policy</Text>
            <Text style={styles.legalAction}>View</Text>
          </Pressable>
        </View>
      </View>

      {/* Session Sign Out */}
      <Pressable
        id="profile-sign-out"
        style={({ pressed }) => [styles.signOut, pressed && styles.signOutPressed]}
        onPress={() => void signOut()}
        accessibilityRole="button"
        accessibilityLabel="Sign out of console"
      >
        <Text style={styles.signOutText}>Sign out of Console</Text>
      </Pressable>

      {/* Legal Document Modal */}
      <Modal
        visible={legalModal !== null}
        animationType="fade"
        transparent
        onRequestClose={() => setLegalModal(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalHeading}>
              {legalModal === 'terms' ? 'Terms of Service' : 'Privacy Policy'}
            </Text>
            <ScrollView style={styles.modalScroll}>
              <Text style={styles.modalBody}>
                {legalModal === 'terms'
                  ? 'By utilizing the Blipp broadcast service, you agree to distribute audio recordings that respect intellectual property rights and applicable communication laws. All streamed media must comply with community safety standards. Audio content is cached and distributed strictly for stream playback.'
                  : 'Blipp protects operator telemetry and audio stream data. Authentication is handled via secure OpenID Connect protocols. No private audio metadata or account telemetry is shared with external commercial data brokers.'}
              </Text>
            </ScrollView>
            <Pressable
              style={styles.modalCloseBtn}
              onPress={() => setLegalModal(null)}
              accessibilityRole="button"
              accessibilityLabel="Close dialog"
            >
              <Text style={styles.modalCloseText}>Close</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
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
    maxWidth: 520,
    width: '100%',
    alignSelf: 'center',
  },
  avatarChassis: {
    marginBottom: 16,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 12,
    backgroundColor: PALETTE.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  avatarText: {
    fontFamily: 'Sora_700Bold',
    fontSize: 26,
    color: PALETTE.text,
  },
  displayName: {
    fontFamily: 'Sora_700Bold',
    fontSize: 20,
    color: PALETTE.text,
    marginBottom: 2,
    letterSpacing: -0.3,
  },
  handle: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: PALETTE.accent,
  },
  email: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    marginTop: 4,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: PALETTE.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: PALETTE.border,
    paddingVertical: 14,
    paddingHorizontal: 20,
    marginTop: 24,
    alignSelf: 'stretch',
  },
  stat: {
    flex: 1,
    alignItems: 'center',
    gap: 4,
  },
  statValue: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
  },
  statLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  statDivider: {
    width: 1,
    height: 28,
    backgroundColor: PALETTE.border,
  },
  section: {
    alignSelf: 'stretch',
    marginTop: 24,
    gap: 10,
  },
  sectionHeading: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  sectionCard: {
    backgroundColor: PALETTE.surface,
    borderRadius: 12,
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
  rowBorder: {
    borderTopWidth: 1,
    borderTopColor: PALETTE.border,
  },
  rowLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  rowValue: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
    flex: 1,
    textAlign: 'right',
  },
  legalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  legalLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  legalAction: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.accent,
  },
  signOut: {
    marginTop: 28,
    alignSelf: 'stretch',
    borderWidth: 1,
    borderColor: `${PALETTE.error}40`,
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    backgroundColor: PALETTE.errorDim,
    minHeight: 48,
    justifyContent: 'center',
  },
  signOutPressed: {
    opacity: 0.75,
  },
  signOutText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.error,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(9, 9, 11, 0.85)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  modalCard: {
    width: '100%',
    maxWidth: 440,
    backgroundColor: PALETTE.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    padding: 24,
    gap: 16,
  },
  modalHeading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 18,
    color: PALETTE.text,
  },
  modalScroll: {
    maxHeight: 240,
  },
  modalBody: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    lineHeight: 22,
  },
  modalCloseBtn: {
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalCloseText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
});
