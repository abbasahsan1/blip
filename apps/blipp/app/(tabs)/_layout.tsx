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
  const bottomOffset = Math.max(insets.bottom, 12);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarShowLabel: false,
        tabBarStyle: [
          styles.floatingPillBar,
          {
            bottom: bottomOffset,
          },
        ],
      }}
    >
      {/* 1. Feed Tab */}
      <Tabs.Screen
        name="index"
        options={{
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Feed" emoji="🔥" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Feed tab',
        }}
      />

      {/* 2. Stash Tab */}
      <Tabs.Screen
        name="saved"
        options={{
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Stash" emoji="🔖" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Stash tab',
        }}
      />

      {/* 3. Drop Tab (Raised Prominent Center Mic Button) */}
      <Tabs.Screen
        name="upload"
        options={{
          tabBarIcon: ({ focused }) => <CenterDropButton focused={focused} />,
          tabBarAccessibilityLabel: 'Drop broadcast tab',
        }}
      />

      {/* 4. Vibes Tab */}
      <Tabs.Screen
        name="vibes"
        options={{
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Vibes" emoji="💬" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Vibes tab',
        }}
      />

      {/* 5. Profile Tab */}
      <Tabs.Screen
        name="profile"
        options={{
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
  floatingPillBar: {
    position: 'absolute',
    left: 16,
    right: 16,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(17, 19, 27, 0.92)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.12)',
    paddingBottom: 0,
    paddingTop: 0,
    alignItems: 'center',
    justifyContent: 'space-around',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.55,
    shadowRadius: 18,
    elevation: 12,
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
    backgroundColor: 'rgba(124, 58, 237, 0.16)',
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
    backgroundColor: PALETTE.accent,
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.9,
    shadowRadius: 4,
  },

  // Raised Center Drop Mic Button
  centerDropWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    top: -12,
  },
  centerDropButton: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: PALETTE.accent,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
    borderColor: PALETTE.bg,
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.7,
    shadowRadius: 12,
    elevation: 8,
  },
  centerDropButtonActive: {
    backgroundColor: PALETTE.magenta,
    shadowColor: PALETTE.magenta,
  },
  centerDropLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 10,
    color: PALETTE.primary,
    marginTop: 2,
  },
  centerDropLabelActive: {
    color: PALETTE.magenta,
  },
});
