import { Tabs } from 'expo-router';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import {
  BookmarkMark,
  MicMark,
  ProfileConsoleMark,
  ShareMark,
} from '@/components/common/Icons';

interface TabItemProps {
  label: string;
  emoji: string;
  focused: boolean;
  children?: React.ReactNode;
}

function FloatingTabItem({ label, emoji, focused, children }: TabItemProps) {
  return (
    <View style={[styles.tabItemContainer, focused && styles.tabItemContainerActive]}>
      <Text style={[styles.tabEmoji, focused && styles.tabEmojiActive]}>{emoji}</Text>
      <Text style={[styles.tabLabel, focused && styles.tabLabelActive]}>{label}</Text>
      {focused && <View style={styles.neonDotIndicator} />}
    </View>
  );
}

function CenterDropButton({ focused }: { focused: boolean }) {
  return (
    <View style={styles.centerDropWrapper}>
      <View style={[styles.centerDropButton, focused && styles.centerDropButtonActive]}>
        <MicMark size={24} color="#FFFFFF" />
      </View>
      <Text style={[styles.centerDropLabel, focused && styles.centerDropLabelActive]}>
        Drop
      </Text>
    </View>
  );
}

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  const barHeight = 56 + insets.bottom;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarShowLabel: false,
        tabBarStyle: [
          styles.frostedBottomBar,
          {
            height: barHeight,
            paddingBottom: insets.bottom,
          },
        ],
      }}
    >
      {/* 1. Feed Tab */}
      <Tabs.Screen
        name="index"
        options={{
          headerShown: false,
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Feed" emoji="🔥" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Feed tab',
        }}
      />

      {/* 2. Drop Tab (Elevated Center Mic Button with neon orange glow) */}
      <Tabs.Screen
        name="upload"
        options={{
          headerShown: false,
          tabBarIcon: ({ focused }) => <CenterDropButton focused={focused} />,
          tabBarAccessibilityLabel: 'Drop broadcast tab',
        }}
      />

      {/* 5. Profile Tab */}
      <Tabs.Screen
        name="profile"
        options={{
          headerShown: false,
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Profile" emoji="👤" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Profile tab',
        }}
      />
    </Tabs>
  );
}

const styles = StyleSheet.create({
  frostedBottomBar: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(7, 8, 11, 0.85)',
    borderTopWidth: 0.5,
    borderTopColor: 'rgba(255, 255, 255, 0.08)',
    alignItems: 'center',
    justifyContent: 'space-around',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 20,
  },
  tabItemContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderRadius: 20,
    position: 'relative',
    minWidth: 50,
  },
  tabItemContainerActive: {
    backgroundColor: 'rgba(234, 88, 12, 0.15)',
  },
  tabEmoji: {
    fontSize: 16,
    opacity: 0.65,
    marginBottom: 2,
  },
  tabEmojiActive: {
    opacity: 1,
    transform: [{ scale: 1.1 }],
  },
  tabLabel: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 10,
    color: PALETTE.textMuted,
  },
  tabLabelActive: {
    fontFamily: 'PlusJakartaSans_700Bold',
    color: '#FFFFFF',
  },
  neonDotIndicator: {
    position: 'absolute',
    bottom: 2,
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.primary,
    shadowColor: PALETTE.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 4,
  },

  // Elevated Center Drop Mic Button with neon orange glow
  centerDropWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    top: -16,
  },
  centerDropButton: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: PALETTE.primary,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: PALETTE.bg,
    shadowColor: PALETTE.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.85,
    shadowRadius: 14,
    elevation: 10,
  },
  centerDropButtonActive: {
    backgroundColor: '#F97316',
    shadowOpacity: 1,
  },
  centerDropLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 10,
    color: '#FFFFFF',
    marginTop: 2,
  },
  centerDropLabelActive: {
    color: '#F97316',
  },
});
