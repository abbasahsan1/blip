import { Tabs } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';

// Simple SVG-free icon set using Unicode + text
function TabIcon({
  label,
  focused,
  icon,
}: {
  label: string;
  focused: boolean;
  icon: string;
}) {
  return (
    <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
      <Text style={[styles.iconGlyph, focused && styles.iconGlyphActive]}>{icon}</Text>
      <Text style={[styles.iconLabel, focused && styles.iconLabelActive]}>{label}</Text>
    </View>
  );
}

export default function TabLayout() {
  const insets = useSafeAreaInsets();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: PALETTE.surface,
          borderTopColor: PALETTE.border,
          borderTopWidth: 1,
          height: 60 + insets.bottom,
          paddingBottom: insets.bottom,
          paddingTop: 8,
          elevation: 0,
        },
        tabBarShowLabel: false,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          tabBarIcon: ({ focused }) => (
            <TabIcon icon="◉" label="Feed" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Feed tab',
        }}
      />
      <Tabs.Screen
        name="upload"
        options={{
          tabBarIcon: ({ focused }) => (
            <TabIcon icon="+" label="Upload" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Upload tab',
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          tabBarIcon: ({ focused }) => (
            <TabIcon icon="◎" label="Profile" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Profile tab',
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  iconWrap: {
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 10,
  },
  iconWrapActive: {
    backgroundColor: PALETTE.accentDim,
  },
  iconGlyph: {
    fontSize: 20,
    color: PALETTE.textMuted,
    lineHeight: 24,
  },
  iconGlyphActive: {
    color: PALETTE.accent,
  },
  iconLabel: {
    fontFamily: 'Inter_500Medium',
    fontSize: 10,
    color: PALETTE.textMuted,
  },
  iconLabelActive: {
    color: PALETTE.accent,
  },
});
