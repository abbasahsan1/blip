import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Link, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { api } from '../../lib/api';
import { useSessionStore } from '../../lib/store/sessionStore';
import { StatusAlertMark } from '@/components/common/Icons';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignUpScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const status = useSessionStore((s) => s.status);
  const setSessionTokens = useSessionStore((s) => s.setSessionTokens);

  // Soundwave animation
  const wave1 = useRef(new Animated.Value(0.35)).current;
  const wave2 = useRef(new Animated.Value(0.75)).current;
  const wave3 = useRef(new Animated.Value(0.55)).current;
  const wave4 = useRef(new Animated.Value(0.95)).current;
  const wave5 = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const createPulse = (val: Animated.Value, duration: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(val, {
            toValue: 1,
            duration,
            useNativeDriver: true,
          }),
          Animated.timing(val, {
            toValue: 0.25,
            duration,
            useNativeDriver: true,
          }),
        ]),
      );

    const a1 = createPulse(wave1, 550);
    const a2 = createPulse(wave2, 420);
    const a3 = createPulse(wave3, 620);
    const a4 = createPulse(wave4, 480);
    const a5 = createPulse(wave5, 590);

    a1.start();
    a2.start();
    a3.start();
    a4.start();
    a5.start();

    return () => {
      a1.stop();
      a2.stop();
      a3.stop();
      a4.stop();
      a5.stop();
    };
  }, [wave1, wave2, wave3, wave4, wave5]);

  useEffect(() => {
    if (status === 'authenticated') {
      router.replace('/(tabs)');
    }
  }, [status, router]);

  async function handleSignUp() {
    if (!username.trim()) {
      setServerError('Please choose a username handle.');
      return;
    }
    if (!email.trim() || !EMAIL_RE.test(email.trim())) {
      setServerError('Please enter a valid email address.');
      return;
    }
    if (!password || password.length < 6) {
      setServerError('Password must be at least 6 characters.');
      return;
    }

    setServerError(null);
    setIsLoading(true);

    try {
      const authResult = await api.register({
        email: email.trim(),
        password,
        username: username.trim(),
        displayName: (displayName.trim() || username.trim()),
      });

      if (authResult?.tokens) {
        await setSessionTokens(authResult.tokens, authResult.user);
        router.replace('/(tabs)');
      } else {
        setServerError('Registration failed. Please try again.');
      }
    } catch (err: any) {
      const msg =
        err?.response?.data?.message ||
        err?.message ||
        'Failed to register account. Please check your details and try again.';
      setServerError(msg);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <View style={styles.container}>
      {/* Immersive Ambient Gradient Canvas */}
      <LinearGradient
        colors={['#07080B', '#11131F', '#07080B']}
        style={StyleSheet.absoluteFill}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 1 }}
      />

      <KeyboardAvoidingView
        style={styles.keyboardAvoid}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={[
            styles.scrollContent,
            { paddingTop: insets.top + 20, paddingBottom: insets.bottom + 24 },
          ]}
          keyboardShouldPersistTaps="handled"
          bounces={false}
        >
          {/* Top 40%: App Branding & Soundwave */}
          <View style={styles.topBrandingSection}>
            <View style={styles.soundwaveCluster}>
              {[wave1, wave2, wave3, wave4, wave5].map((w, idx) => (
                <Animated.View
                  key={idx}
                  style={[
                    styles.soundwaveBar,
                    {
                      transform: [{ scaleY: w }],
                      backgroundColor: idx % 2 === 0 ? '#8B5CF6' : '#EC4899',
                    },
                  ]}
                />
              ))}
            </View>

            <Text style={styles.brandTitle}>BLIPPS</Text>
            <Text style={styles.brandTagline}>Drop in. Speak up.</Text>
          </View>

          {/* Bottom 60%: Native Bottom Sheet Form */}
          <View style={styles.bottomSheetCard}>
            <View style={styles.sheetHandle} />

            <Text style={styles.sheetTitle}>Create Account</Text>
            <Text style={styles.sheetSubtitle}>Join the next-gen audio-social community</Text>

            {/* Error Banner */}
            {serverError && (
              <View style={styles.errorContainer} accessibilityRole="alert">
                <StatusAlertMark size={16} color="#EF4444" />
                <Text style={styles.errorText}>{serverError}</Text>
              </View>
            )}

            {/* Username Input */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Username Handle</Text>
              <TextInput
                style={[
                  styles.pillInput,
                  focusedField === 'username' && styles.pillInputFocused,
                ]}
                value={username}
                onChangeText={(text) => {
                  setUsername(text);
                  if (serverError) setServerError(null);
                }}
                onFocus={() => setFocusedField('username')}
                onBlur={() => setFocusedField(null)}
                placeholder="creator_handle"
                placeholderTextColor="rgba(255, 255, 255, 0.3)"
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
              />
            </View>

            {/* Display Name Input */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Display Name</Text>
              <TextInput
                style={[
                  styles.pillInput,
                  focusedField === 'displayName' && styles.pillInputFocused,
                ]}
                value={displayName}
                onChangeText={(text) => {
                  setDisplayName(text);
                  if (serverError) setServerError(null);
                }}
                onFocus={() => setFocusedField('displayName')}
                onBlur={() => setFocusedField(null)}
                placeholder="Alex Rivers"
                placeholderTextColor="rgba(255, 255, 255, 0.3)"
                returnKeyType="next"
              />
            </View>

            {/* Email Input */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Email Address</Text>
              <TextInput
                style={[
                  styles.pillInput,
                  focusedField === 'email' && styles.pillInputFocused,
                ]}
                value={email}
                onChangeText={(text) => {
                  setEmail(text);
                  if (serverError) setServerError(null);
                }}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                placeholder="alex@blipp.com"
                placeholderTextColor="rgba(255, 255, 255, 0.3)"
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
              />
            </View>

            {/* Password Input */}
            <View style={styles.inputGroup}>
              <Text style={styles.inputLabel}>Password</Text>
              <TextInput
                style={[
                  styles.pillInput,
                  focusedField === 'password' && styles.pillInputFocused,
                ]}
                value={password}
                onChangeText={(text) => {
                  setPassword(text);
                  if (serverError) setServerError(null);
                }}
                onFocus={() => setFocusedField('password')}
                onBlur={() => setFocusedField(null)}
                placeholder="Minimum 6 characters"
                placeholderTextColor="rgba(255, 255, 255, 0.3)"
                secureTextEntry
                autoCapitalize="none"
                returnKeyType="done"
                onSubmitEditing={handleSignUp}
              />
            </View>

            {/* Primary Action Button (Violet-to-Pink gradient) */}
            <Pressable
              onPress={handleSignUp}
              disabled={isLoading}
              style={({ pressed }) => [
                styles.submitButtonWrapper,
                pressed && styles.buttonPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel="Create Account"
            >
              <LinearGradient
                colors={['#8B5CF6', '#EC4899']}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={styles.submitGradient}
              >
                {isLoading ? (
                  <ActivityIndicator color="#FFFFFF" size="small" />
                ) : (
                  <Text style={styles.submitButtonText}>Create Account</Text>
                )}
              </LinearGradient>
            </Pressable>

            {/* Switch to Sign In */}
            <View style={styles.switchAuthRow}>
              <Text style={styles.switchAuthPrompt}>Already have an account? </Text>
              <Link href="/auth/sign-in" asChild>
                <Pressable hitSlop={8}>
                  <Text style={styles.switchAuthLink}>Sign In</Text>
                </Pressable>
              </Link>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#07080B',
  },
  keyboardAvoid: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'space-between',
  },

  // Top 40% Branding
  topBrandingSection: {
    height: 180,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  soundwaveCluster: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 40,
    gap: 6,
    marginBottom: 12,
  },
  soundwaveBar: {
    width: 6,
    height: 36,
    borderRadius: 3,
  },
  brandTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 34,
    color: '#FFFFFF',
    letterSpacing: 4,
    textShadowColor: 'rgba(139, 92, 246, 0.65)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 18,
  },
  brandTagline: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.65)',
    marginTop: 4,
    letterSpacing: 0.5,
  },

  // Bottom 60% Modern Sheet
  bottomSheetCard: {
    backgroundColor: '#0E111A',
    borderTopLeftRadius: 36,
    borderTopRightRadius: 36,
    borderWidth: 1,
    borderColor: '#1F2433',
    paddingHorizontal: 24,
    paddingTop: 16,
    paddingBottom: 36,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -8 },
    shadowOpacity: 0.6,
    shadowRadius: 24,
    elevation: 20,
  },
  sheetHandle: {
    width: 44,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    alignSelf: 'center',
    marginBottom: 16,
  },
  sheetTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 24,
    color: '#FFFFFF',
    letterSpacing: -0.5,
  },
  sheetSubtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: 'rgba(255, 255, 255, 0.5)',
    marginTop: 4,
    marginBottom: 18,
  },

  // Form Fields
  inputGroup: {
    marginBottom: 14,
  },
  inputLabel: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: 'rgba(255, 255, 255, 0.75)',
    marginBottom: 6,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  pillInput: {
    backgroundColor: '#161922',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#262B3A',
    height: 50,
    paddingHorizontal: 20,
    color: '#FFFFFF',
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 15,
  },
  pillInputFocused: {
    borderColor: '#8B5CF6',
    backgroundColor: '#191D28',
    shadowColor: '#8B5CF6',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.35,
    shadowRadius: 8,
  },

  // Error Banner
  errorContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.35)',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 14,
    gap: 8,
  },
  errorText: {
    flex: 1,
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: '#F87171',
  },

  // Primary Action Button
  submitButtonWrapper: {
    marginTop: 10,
    borderRadius: 24,
    height: 54,
    overflow: 'hidden',
    shadowColor: '#8B5CF6',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.45,
    shadowRadius: 14,
    elevation: 8,
  },
  submitGradient: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitButtonText: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 16,
    color: '#FFFFFF',
    letterSpacing: 0.5,
  },
  buttonPressed: {
    opacity: 0.88,
    transform: [{ scale: 0.985 }],
  },

  // Footer Navigation
  switchAuthRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 20,
  },
  switchAuthPrompt: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: 'rgba(255, 255, 255, 0.55)',
  },
  switchAuthLink: {
    fontFamily: 'PlusJakartaSans_700Bold',
    fontSize: 14,
    color: '#A78BFA',
  },
});
