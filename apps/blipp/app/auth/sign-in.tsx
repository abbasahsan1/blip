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

  const [step, setStep] = useState<'email' | 'otp'>('email');
  const [email, setEmail] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [touched, setTouched] = useState({ email: false, otp: false });
  const [resendCooldown, setResendCooldown] = useState(0);

  const isSubmitting = useSessionStore((s) => s.isSubmitting);
  const error = useSessionStore((s) => s.error);
  const status = useSessionStore((s) => s.status);
  const requestOtp = useSessionStore((s) => s.requestOtp);
  const verifyOtp = useSessionStore((s) => s.verifyOtp);
  const signInWithOAuth = useSessionStore((s) => s.signInWithOAuth);
  const clearError = useSessionStore((s) => s.clearError);

  // Navigate away when authenticated
  useEffect(() => {
    if (status === 'authenticated') {
      router.replace('/(tabs)');
    }
  }, [status, router]);

  useEffect(() => {
    clearError();
  }, [clearError, step]);

  // Resend cooldown timer
  useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown((c) => c - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [resendCooldown]);

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
    touched.email && !EMAIL_RE.test(email.trim()) ? 'Enter a valid email address' : null;
  const otpError =
    touched.otp && otpCode.trim().length !== 6 ? 'Enter the 6-digit verification code' : null;
  const authError = error?.message || null;

  const canRequestCode = EMAIL_RE.test(email.trim()) && !isSubmitting;
  const canVerify = otpCode.trim().length === 6 && !isSubmitting;

  async function handleSendCode() {
    setTouched((t) => ({ ...t, email: true }));
    if (!canRequestCode) return;
    const ok = await requestOtp(email.trim().toLowerCase());
    if (ok) {
      setStep('otp');
      setResendCooldown(30);
    }
  }

  async function handleVerifyCode() {
    setTouched((t) => ({ ...t, otp: true }));
    if (!canVerify) return;
    await verifyOtp(email.trim().toLowerCase(), otpCode.trim());
  }

  async function handleAppleSignIn() {
    await signInWithOAuth('apple');
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
          <Text style={styles.heading}>
            {step === 'email' ? 'Welcome to Blipp' : 'Check your email'}
          </Text>
          <Text style={styles.subheading}>
            {step === 'email'
              ? 'Passwordless login with Email & OTP'
              : `We sent a 6-digit code to ${email}`}
          </Text>

          {/* Auth error banner */}
          {authError && (
            <View style={styles.errorBanner}>
              <Text style={styles.errorBannerText}>{authError}</Text>
            </View>
          )}

          {step === 'email' ? (
            <>
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
                  returnKeyType="done"
                  onSubmitEditing={handleSendCode}
                  accessibilityLabel="Email address"
                />
                {emailError && <Text style={styles.fieldError}>{emailError}</Text>}
              </View>

              {/* Continue with Email button */}
              <Pressable
                id="sign-in-send-code"
                style={({ pressed }) => [
                  styles.button,
                  pressed && styles.buttonPressed,
                  !canRequestCode && styles.buttonDisabled,
                ]}
                onPress={handleSendCode}
                disabled={!canRequestCode}
                accessibilityRole="button"
                accessibilityLabel="Send verification code"
              >
                <Text style={styles.buttonText}>
                  {isSubmitting ? 'Sending code…' : 'Continue with Email'}
                </Text>
              </Pressable>

              {/* Divider */}
              <View style={styles.divider}>
                <View style={styles.dividerLine} />
                <Text style={styles.dividerText}>or continue with</Text>
                <View style={styles.dividerLine} />
              </View>

              {/* Federated OAuth Buttons */}
              <View style={styles.oauthRow}>
                <GoogleSignInButton />
                <Pressable
                  style={({ pressed }) => [
                    styles.appleButton,
                    pressed && styles.buttonPressed,
                  ]}
                  onPress={handleAppleSignIn}
                  accessibilityRole="button"
                  accessibilityLabel="Continue with Apple"
                >
                  <Text style={styles.appleButtonText}> Apple</Text>
                </Pressable>
              </View>

              {/* Footer */}
              <View style={styles.footer}>
                <Text style={styles.footerText}>New to Blipp?{' '}</Text>
                <Link href="/auth/sign-up" asChild>
                  <Pressable accessibilityRole="link">
                    <Text style={styles.footerLink}>Create account</Text>
                  </Pressable>
                </Link>
              </View>
            </>
          ) : (
            <>
              {/* OTP Code */}
              <View style={styles.field}>
                <View style={styles.otpHeaderRow}>
                  <Text style={styles.label}>Verification Code</Text>
                  <Pressable onPress={() => setStep('email')}>
                    <Text style={styles.changeEmailText}>Change email</Text>
                  </Pressable>
                </View>
                <TextInput
                  id="sign-in-otp"
                  style={[styles.input, styles.otpInput, otpError ? styles.inputError : null]}
                  value={otpCode}
                  onChangeText={(text) => setOtpCode(text.replace(/[^0-9]/g, '').slice(0, 6))}
                  placeholder="123456"
                  placeholderTextColor={PALETTE.textMuted}
                  keyboardType="number-pad"
                  maxLength={6}
                  returnKeyType="done"
                  onSubmitEditing={handleVerifyCode}
                  accessibilityLabel="Verification Code"
                  autoFocus
                />
                {otpError && <Text style={styles.fieldError}>{otpError}</Text>}
              </View>

              {/* Verify & Sign In button */}
              <Pressable
                id="sign-in-verify-code"
                style={({ pressed }) => [
                  styles.button,
                  pressed && styles.buttonPressed,
                  !canVerify && styles.buttonDisabled,
                ]}
                onPress={handleVerifyCode}
                disabled={!canVerify}
                accessibilityRole="button"
                accessibilityLabel="Verify and sign in"
              >
                <Text style={styles.buttonText}>
                  {isSubmitting ? 'Verifying…' : 'Verify & Sign In'}
                </Text>
              </Pressable>

              {/* Resend code */}
              <View style={styles.resendRow}>
                <Pressable
                  disabled={resendCooldown > 0 || isSubmitting}
                  onPress={handleSendCode}
                >
                  <Text
                    style={[
                      styles.resendText,
                      resendCooldown > 0 && styles.resendTextDisabled,
                    ]}
                  >
                    {resendCooldown > 0
                      ? `Resend code in ${resendCooldown}s`
                      : 'Resend code'}
                  </Text>
                </Pressable>
              </View>
            </>
          )}
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
  otpHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  changeEmailText: {
    fontFamily: 'Inter_500Medium',
    fontSize: 12,
    color: PALETTE.accent,
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
  otpInput: {
    fontSize: 22,
    letterSpacing: 8,
    textAlign: 'center',
    fontFamily: 'Inter_700Bold',
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
  // OAuth
  oauthRow: {
    flexDirection: 'column',
    gap: 10,
  },
  appleButton: {
    backgroundColor: '#18181b',
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  appleButtonText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  resendRow: {
    alignItems: 'center',
    marginTop: 6,
  },
  resendText: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: PALETTE.accent,
  },
  resendTextDisabled: {
    color: PALETTE.textMuted,
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
