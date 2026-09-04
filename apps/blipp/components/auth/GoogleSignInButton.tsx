import { Pressable, StyleSheet, Text, View } from 'react-native';
import { PALETTE } from '@/lib/palette';

interface Props {
  onPress?: () => void;
}

/**
 * Google Sign-In button.
 * Phase 1: disabled — Google OAuth credentials not yet configured.
 * Phase 1.5: when GOOGLE_CLIENT_ID/SECRET are provided, this will trigger
 *   Keycloak's /realms/blipp/broker/google/endpoint flow via in-app browser.
 */
export function GoogleSignInButton({ onPress }: Props) {
  return (
    <View style={styles.wrap}>
      <Pressable
        id="google-sign-in-btn"
        style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        onPress={onPress}
        disabled={!onPress}
        accessibilityRole="button"
        accessibilityLabel="Continue with Google (coming soon)"
        accessibilityHint="Google sign-in will be available soon"
      >
        {/* Google G */}
        <View style={styles.gLogo}>
          <Text style={styles.gText}>G</Text>
        </View>
        <Text style={styles.btnText}>Continue with Google</Text>
        <View style={styles.comingSoon}>
          <Text style={styles.comingSoonText}>Soon</Text>
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
    backgroundColor: PALETTE.glass,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    gap: 12,
    minHeight: 50,
    opacity: 0.5,
  },
  btnPressed: {
    opacity: 0.35,
  },
  gLogo: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  gText: {
    fontSize: 14,
    fontFamily: 'Inter_700Bold',
    color: '#4285F4',
    lineHeight: 18,
  },
  btnText: {
    flex: 1,
    fontFamily: 'Inter_500Medium',
    fontSize: 15,
    color: PALETTE.textSecondary,
  },
  comingSoon: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    backgroundColor: PALETTE.accentDim,
    borderWidth: 1,
    borderColor: PALETTE.accent,
  },
  comingSoonText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 10,
    color: PALETTE.accent,
  },
});
