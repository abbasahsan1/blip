import { useEffect, useRef, useState } from 'react';
import {
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
import { useSessionStore } from '@/lib/store/sessionStore';
import { PALETTE } from '@/lib/palette';
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignInScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState({ email: false, password: false });

  const isSubmitting = useSessionStore((s) => s.isSubmitting);
  const error = useSessionStore((s) => s.error);
  const status = useSessionStore((s) => s.status);
  const signInWithEmail = useSessionStore((s) => s.signInWithEmail);
  const clearError = useSessionStore((s) => s.clearError);

  // Navigate away when authenticated
  useEffect(() => {
    if (status === 'authenticated') {
      router.replace('/(tabs)');
    }
  }, [status, router]);

  useEffect(() => {
    clearError();
  }, [clearError]);

  // Waveform animation
  const bars = useRef(Array.from({ length: 24 }, () => new Animated.Value(0.3))).current;

  useEffect(() => {
    const animations = bars.map((bar, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 60),
          Animated.timing(bar, {
            toValue: 0.2 + Math.random() * 0.8,
            duration: 600 + Math.random() * 400,
            useNativeDriver: false,
          }),
          Animated.timing(bar, {
            toValue: 0.1 + Math.random() * 0.3,
            duration: 400 + Math.random() * 300,
            useNativeDriver: false,
          }),
        ]),
      ),
    );
    Animated.parallel(animations).start();
    return () => animations.forEach((a) => a.stop());
  }, [bars]);

  const emailError =
    touched.email && !EMAIL_RE.test(email) ? 'Enter a valid email address' : null;
  const passwordError = touched.password && password.length < 6 ? 'Password is too short' : null;
  const authError =
    error?.field === 'credentials' || error?.field === 'general' ? error.message : null;

  const canSubmit = EMAIL_RE.test(email) && password.length >= 6 && !isSubmitting;

  async function handleSignIn() {
    setTouched({ email: true, password: true });
    if (!canSubmit) return;
    await signInWithEmail(email.trim().toLowerCase(), password);
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 32, paddingBottom: insets.bottom + 32 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Logo / Brand */}
        <View style={styles.brand}>
          <Text style={styles.logo}>blipp</Text>
          <Text style={styles.tagline}>Audio worth hearing</Text>

          {/* Waveform motif */}
          <View style={styles.waveform} aria-hidden>
            {bars.map((bar, i) => (
              <Animated.View
                key={i}
                style={[
                  styles.waveBar,
                  {
                    height: bar.interpolate({
                      inputRange: [0, 1],
                      outputRange: ['4%', '100%'],
                    }),
                    backgroundColor:
                      i % 3 === 0 ? PALETTE.accent : i % 3 === 1 ? '#8b5cf6' : '#a78bfa',
                    opacity: bar.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0.3, 0.9],
                    }),
                  },
                ]}
              />
            ))}
          </View>
        </View>

        {/* Card */}
        <View style={styles.card}>
          <Text style={styles.heading}>Welcome back</Text>
          <Text style={styles.subheading}>Sign in to your account</Text>

          {/* Auth error banner */}
          {authError && (
            <View style={styles.errorBanner}>
              <Text style={styles.errorBannerText}>{authError}</Text>
            </View>
          )}

          {/* Email */}
          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              id="sign-in-email"
              style={[styles.input, emailError ? styles.inputError : null]}
              value={email}
              onChangeText={setEmail}
              onBlur={() => setTouched((t) => ({ ...t, email: true }))}
              placeholder="you@example.com"
              placeholderTextColor={PALETTE.textMuted}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
              autoCorrect={false}
              textContentType="emailAddress"
              returnKeyType="next"
              accessibilityLabel="Email address"
            />
            {emailError && <Text style={styles.fieldError}>{emailError}</Text>}
          </View>

          {/* Password */}
          <View style={styles.field}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              id="sign-in-password"
              style={[styles.input, passwordError ? styles.inputError : null]}
              value={password}
              onChangeText={setPassword}
              onBlur={() => setTouched((t) => ({ ...t, password: true }))}
              placeholder="••••••••"
              placeholderTextColor={PALETTE.textMuted}
              secureTextEntry
              autoComplete="current-password"
              textContentType="password"
              returnKeyType="done"
              onSubmitEditing={handleSignIn}
              accessibilityLabel="Password"
            />
            {passwordError && <Text style={styles.fieldError}>{passwordError}</Text>}
          </View>

          {/* Sign in button */}
          <Pressable
            id="sign-in-submit"
            style={({ pressed }) => [
              styles.button,
              pressed && styles.buttonPressed,
              !canSubmit && styles.buttonDisabled,
            ]}
            onPress={handleSignIn}
            disabled={!canSubmit}
            accessibilityRole="button"
            accessibilityLabel="Sign in"
          >
            <Text style={styles.buttonText}>
              {isSubmitting ? 'Signing in…' : 'Sign in'}
            </Text>
          </Pressable>

          {/* Divider */}
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>

          {/* Google */}
          <GoogleSignInButton />

          {/* Sign up link */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Don't have an account?{' '}</Text>
            <Link href="/auth/sign-up" asChild>
              <Pressable accessibilityRole="link">
                <Text style={styles.footerLink}>Create one</Text>
              </Pressable>
            </Link>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: 24,
    alignItems: 'stretch',
  },
  // Brand
  brand: {
    alignItems: 'center',
    marginBottom: 40,
  },
  logo: {
    fontFamily: 'Inter_700Bold',
    fontSize: 48,
    color: PALETTE.text,
    letterSpacing: -2,
  },
  tagline: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
    marginTop: 4,
    letterSpacing: 0.5,
  },
  waveform: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 48,
    gap: 3,
    marginTop: 24,
    width: '100%',
    maxWidth: 320,
  },
  waveBar: {
    flex: 1,
    borderRadius: 2,
    minHeight: 4,
  },
  // Card
  card: {
    backgroundColor: PALETTE.surface,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: PALETTE.glassBorder,
    padding: 28,
    gap: 16,
  },
  heading: {
    fontFamily: 'Inter_700Bold',
    fontSize: 22,
    color: PALETTE.text,
  },
  subheading: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    marginTop: -8,
  },
  // Error banner
  errorBanner: {
    backgroundColor: PALETTE.errorDim,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: `${PALETTE.error}40`,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  errorBannerText: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: PALETTE.error,
  },
  // Fields
  field: {
    gap: 6,
  },
  label: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },
  input: {
    backgroundColor: PALETTE.glass,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontFamily: 'Inter_400Regular',
    fontSize: 15,
    color: PALETTE.text,
    minHeight: 50,
  },
  inputError: {
    borderColor: PALETTE.error,
  },
  fieldError: {
    fontFamily: 'Inter_400Regular',
    fontSize: 12,
    color: PALETTE.error,
  },
  // Button
  button: {
    backgroundColor: PALETTE.accent,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 4,
    minHeight: 52,
    justifyContent: 'center',
  },
  buttonPressed: {
    opacity: 0.85,
    transform: [{ scale: 0.98 }],
  },
  buttonDisabled: {
    opacity: 0.4,
  },
  buttonText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 15,
    color: '#fff',
    letterSpacing: 0.3,
  },
  // Divider
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: PALETTE.border,
  },
  dividerText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
  },
  // Footer
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    flexWrap: 'wrap',
    marginTop: 4,
  },
  footerText: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
  },
  footerLink: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 14,
    color: PALETTE.accent,
  },
});
