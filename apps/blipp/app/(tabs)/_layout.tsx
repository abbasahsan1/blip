import { Tabs } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import {
  FeedConsoleMark,
  UploadConsoleMark,
  ProfileConsoleMark,
  BookmarkMark,
} from '@/components/common/Icons';

function TabIcon({
  label,
  focused,
  children,
}: {
  label: string;
  focused: boolean;
  children: React.ReactNode;
}) {
  return (
    <View style={[styles.iconWrap, focused && styles.iconWrapActive]}>
      {children}
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
            <TabIcon label="Feed" focused={focused}>
              <FeedConsoleMark
                size={20}
                color={focused ? PALETTE.accent : PALETTE.textMuted}
              />
            </TabIcon>
          ),
          tabBarAccessibilityLabel: 'Feed console tab',
        }}
      />
      <Tabs.Screen
        name="saved"
        options={{
          tabBarIcon: ({ focused }) => (
            <TabIcon label="Saved" focused={focused}>
              <BookmarkMark
                size={20}
                color={focused ? PALETTE.accent : PALETTE.textMuted}
                filled={focused}
              />
            </TabIcon>
          ),
          tabBarAccessibilityLabel: 'Saved blipps tab',
        }}
      />
      <Tabs.Screen
        name="upload"
        options={{
          tabBarIcon: ({ focused }) => (
            <TabIcon label="Upload" focused={focused}>
              <UploadConsoleMark
                size={20}
                color={focused ? PALETTE.accent : PALETTE.textMuted}
              />
            </TabIcon>
          ),
          tabBarAccessibilityLabel: 'Upload audio tab',
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          tabBarIcon: ({ focused }) => (
            <TabIcon label="Profile" focused={focused}>
              <ProfileConsoleMark
                size={20}
                color={focused ? PALETTE.accent : PALETTE.textMuted}
              />
            </TabIcon>
          ),
          tabBarAccessibilityLabel: 'Profile console tab',
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  iconWrap: {
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 16,
    paddingVertical: 4,
    borderRadius: 8,
  },
  iconWrapActive: {
    backgroundColor: PALETTE.accentDim,
  },
  iconLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 11,
    color: PALETTE.textMuted,
  },
  iconLabelActive: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    color: PALETTE.accent,
  },
});
