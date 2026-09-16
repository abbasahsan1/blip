import { type ExpoConfig, type ConfigContext } from 'expo/config';

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Blipp',
  slug: 'blipp',
  version: '1.0.0',
  scheme: 'blipp',
  web: {
    bundler: 'metro',
    output: 'single',
    favicon: './assets/favicon.png',
  },
  plugins: [
    'expo-router',
    'expo-secure-store',
    [
      'expo-splash-screen',
      {
        backgroundColor: '#09090b',
        image: './assets/splash.png',
        imageWidth: 200,
      },
    ],
    [
      'expo-audio',
      {
        microphonePermission: 'Allow Blipp to access your microphone for recording voice blipps and stories.',
        recordAudioAndroid: true,
      },
    ],
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    router: {
      origin: false,
    },
  },
});
