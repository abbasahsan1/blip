import { Stack } from 'expo-router';
import { PALETTE } from '@/lib/palette';

export default function MessagesLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: PALETTE.bg },
      }}
    />
  );
}
