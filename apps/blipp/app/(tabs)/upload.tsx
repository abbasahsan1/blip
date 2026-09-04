import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';

export default function UploadScreen() {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={[
        styles.root,
        { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 },
      ]}
    >
      <View style={styles.icon}>
        <Text style={styles.iconText}>🎙</Text>
      </View>
      <Text style={styles.heading}>Share a Blipp</Text>
      <Text style={styles.body}>
        Upload short audio clips from podcasts, interviews, or anything worth hearing.
        {'\n\n'}
        Audio upload is coming in the next release.
      </Text>
      <View style={styles.badge}>
        <Text style={styles.badgeText}>Phase 3</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: PALETTE.bg,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  icon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  iconText: {
    fontSize: 36,
  },
  heading: {
    fontFamily: 'Inter_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    marginBottom: 12,
    textAlign: 'center',
  },
  body: {
    fontFamily: 'Inter_400Regular',
    fontSize: 15,
    color: PALETTE.textMuted,
    textAlign: 'center',
    lineHeight: 22,
  },
  badge: {
    marginTop: 24,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 20,
    backgroundColor: PALETTE.accentDim,
    borderWidth: 1,
    borderColor: PALETTE.accent,
  },
  badgeText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 12,
    color: PALETTE.accent,
  },
});
