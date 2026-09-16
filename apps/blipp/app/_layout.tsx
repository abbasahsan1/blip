import { useFonts } from 'expo-font';
import {
  Sora_700Bold,
} from '@expo-google-fonts/sora';
import {
  Outfit_400Regular,
  Outfit_500Medium,
  Outfit_600SemiBold,
  Outfit_700Bold,
} from '@expo-google-fonts/outfit';
import { SplashScreen, Stack, useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import { View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { useSessionStore } from '@/lib/store/sessionStore';
import { useFeedStore } from '@/lib/store/feedStore';
import { PALETTE } from '@/lib/palette';

void SplashScreen.preventAutoHideAsync();

function RootNavigator() {
  const status = useSessionStore((s) => s.status);
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    if (status === 'loading') return;

    const inAuth = segments[0] === 'auth';

    if (status === 'authenticated' && inAuth) {
      router.replace('/(tabs)');
    } else if (status === 'unauthenticated' && !inAuth) {
      router.replace('/auth/sign-in');
    }
  }, [status, segments, router]);

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: PALETTE.bg },
        animation: 'fade',
      }}
    >
      <Stack.Screen name="auth" />
      <Stack.Screen name="(tabs)" />
      <Stack.Screen name="messages" options={{ animation: 'slide_from_right' }} />
      <Stack.Screen name="+not-found" />
    </Stack>
  );
}

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    Sora_700Bold,
    Outfit_400Regular,
    Outfit_500Medium,
    Outfit_600SemiBold,
    Outfit_700Bold,
  });

  const status = useSessionStore((s) => s.status);
  const initialize = useSessionStore((s) => s.initialize);
  const loadFeed = useFeedStore((s) => s.loadFeed);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  useEffect(() => {
    if (status === 'authenticated') {
      void loadFeed();
    }
  }, [status, loadFeed]);

  useEffect(() => {
    if ((fontsLoaded || fontError) && status !== 'loading') {
      void SplashScreen.hideAsync();
    }
  }, [fontsLoaded, fontError, status]);

  if ((!fontsLoaded && !fontError) || status === 'loading') {
    return (
      <View style={{ flex: 1, backgroundColor: PALETTE.bg }} />
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <RootNavigator />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
