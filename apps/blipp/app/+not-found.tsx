import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';

export default function NotFoundScreen() {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <Text style={styles.code}>404</Text>
      <Text style={styles.heading}>Signal lost</Text>
      <Text style={styles.sub}>No audio track found on this frequency.</Text>
      <Link href="/" style={styles.link}>
        <Text style={styles.linkText}>Return to Sound Deck</Text>
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: PALETTE.bg,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingHorizontal: 24,
  },
  code: {
    fontFamily: 'Sora_700Bold',
    fontSize: 64,
    color: PALETTE.border,
    letterSpacing: -3,
  },
  heading: {
    fontFamily: 'Sora_600SemiBold',
    fontSize: 18,
    color: PALETTE.text,
  },
  sub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
    textAlign: 'center',
  },
  link: {
    marginTop: 12,
  },
  linkText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.accent,
  },
});
