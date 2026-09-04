import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';

export default function NotFoundScreen() {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <Text style={styles.code}>404</Text>
      <Text style={styles.heading}>Nothing here</Text>
      <Link href="/" style={styles.link}>
        <Text style={styles.linkText}>Go home</Text>
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
    gap: 12,
  },
  code: {
    fontFamily: 'Inter_700Bold',
    fontSize: 64,
    color: PALETTE.border,
    letterSpacing: -4,
  },
  heading: {
    fontFamily: 'Inter_500Medium',
    fontSize: 18,
    color: PALETTE.textMuted,
  },
  link: {
    marginTop: 8,
  },
  linkText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 15,
    color: PALETTE.accent,
  },
});
