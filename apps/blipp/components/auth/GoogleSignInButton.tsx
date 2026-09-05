import { Pressable, StyleSheet, Text, View } from 'react-native';
import { PALETTE } from '@/lib/palette';

interface Props {
  onPress?: () => void;
}

export function GoogleSignInButton({ onPress }: Props) {
  return (
    <View style={styles.wrap}>
      <Pressable
        id="google-sign-in-btn"
        style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        onPress={onPress}
        disabled={!onPress}
        accessibilityRole="button"
        accessibilityLabel="Continue with Google"
        accessibilityHint="Google authentication is scheduled for upcoming release"
      >
        <View style={styles.gLogo}>
          <Text style={styles.gText}>G</Text>
        </View>
        <Text style={styles.btnText}>Continue with Google</Text>
        <View style={styles.comingSoon}>
          <Text style={styles.comingSoonText}>Scheduled</Text>
        </View>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 6,
  },
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 16,
    gap: 12,
    minHeight: 48,
    opacity: 0.6,
  },
  btnPressed: {
    opacity: 0.4,
  },
  gLogo: {
    width: 22,
    height: 22,
    borderRadius: 4,
    backgroundColor: '#ffffff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  gText: {
    fontSize: 13,
    fontFamily: 'Sora_700Bold',
    color: '#4285F4',
    lineHeight: 16,
  },
  btnText: {
    flex: 1,
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  comingSoon: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  comingSoonText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
});
