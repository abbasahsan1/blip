import { Tabs } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import { Feather } from '@expo/vector-icons';

interface TabItemProps {
  label: string;
  iconName: keyof typeof Feather.glyphMap;
  focused: boolean;
}

function FloatingTabItem({ label, iconName, focused }: TabItemProps) {
  return (
    <View style={styles.tabItemContainer}>
      <Feather 
        name={iconName} 
        size={22} 
        color={focused ? PALETTE.primary : PALETTE.textSecondary} 
      />
      <Text style={[styles.tabLabel, focused && styles.tabLabelActive]}>{label}</Text>
    </View>
  );
}

function CenterDropButton({ focused }: { focused: boolean }) {
  return (
    <View style={styles.centerDropWrapper}>
      <Feather 
        name="plus" 
        size={32} 
        color={focused ? PALETTE.primary : PALETTE.textPrimary} 
        style={focused ? styles.centerDropIconActive : styles.centerDropIcon}
      />
    </View>
  );
}

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  const barHeight = 60 + insets.bottom;

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
      <Tabs.Screen
        name="index"
        options={{
          headerShown: false,
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Feed" iconName="home" focused={focused} />
          ),
          tabBarAccessibilityLabel: 'Feed tab',
        }}
      />

      <Tabs.Screen
        name="upload"
        options={{
          headerShown: false,
          tabBarIcon: ({ focused }) => <CenterDropButton focused={focused} />,
          tabBarAccessibilityLabel: 'Drop broadcast tab',
        }}
      />

      <Tabs.Screen
        name="profile"
        options={{
          headerShown: false,
          tabBarIcon: ({ focused }) => (
            <FloatingTabItem label="Profile" iconName="user" focused={focused} />
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
    backgroundColor: 'rgba(0, 0, 0, 0.85)',
    borderTopWidth: 0,
    alignItems: 'center',
    justifyContent: 'space-around',
    elevation: 0,
  },
  tabItemContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    minWidth: 60,
  },
  tabLabel: {
    fontFamily: 'Outfit_500Medium',
    fontSize: 10,
    color: PALETTE.textSecondary,
    marginTop: 4,
  },
  tabLabelActive: {
    fontFamily: 'Outfit_700Bold',
    color: PALETTE.primary,
  },
  centerDropWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    top: 5,
  },
  centerDropIcon: {
    opacity: 0.8,
  },
  centerDropIconActive: {
    opacity: 1,
    shadowColor: PALETTE.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 8,
  },
});
