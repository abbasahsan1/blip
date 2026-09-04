import { useEffect, useState } from 'react';
import {
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

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignUpScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [touched, setTouched] = useState({
    username: false,
    email: false,
    password: false,
    confirmPassword: false,
  });

  const isSubmitting = useSessionStore((s) => s.isSubmitting);
  const error = useSessionStore((s) => s.error);
  const status = useSessionStore((s) => s.status);
  const signUpWithEmail = useSessionStore((s) => s.signUpWithEmail);
  const clearError = useSessionStore((s) => s.clearError);

  useEffect(() => {
    if (status === 'authenticated') router.replace('/(tabs)');
  }, [status, router]);

  useEffect(() => {
    clearError();
  }, [clearError]);

  const usernameError =
    touched.username && username.trim().length < 3
      ? 'Username must be at least 3 characters'
      : null;
  const emailError =
    touched.email && !EMAIL_RE.test(email) ? 'Enter a valid email address' : null;
  const passwordError =
    touched.password && password.length < 8 ? 'Password must be at least 8 characters' : null;
  const confirmError =
    touched.confirmPassword && confirmPassword !== password ? 'Passwords do not match' : null;

  const authError =
    error?.field === 'general' || error?.field === 'email' || error?.field === 'username'
      ? error.message
      : null;

  const canSubmit =
    username.trim().length >= 3 &&
    EMAIL_RE.test(email) &&
    password.length >= 8 &&
    confirmPassword === password &&
    !isSubmitting;

  async function handleSignUp() {
    setTouched({ username: true, email: true, password: true, confirmPassword: true });
    if (!canSubmit) return;
    await signUpWithEmail(username.trim(), email.trim().toLowerCase(), password);
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 32 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.brand}>
          <Text style={styles.logo}>blipp</Text>
          <Text style={styles.tagline}>Audio worth hearing</Text>
        </View>

        {/* Card */}
        <View style={styles.card}>
          <Text style={styles.heading}>Create account</Text>
          <Text style={styles.subheading}>Start listening in seconds</Text>

          {authError && (
            <View style={styles.errorBanner}>
              <Text style={styles.errorBannerText}>{authError}</Text>
            </View>
          )}

          {/* Username */}
          <View style={styles.field}>
            <Text style={styles.label}>Username</Text>
            <TextInput
              id="sign-up-username"
              style={[styles.input, usernameError ? styles.inputError : null]}
              value={username}
              onChangeText={setUsername}
              onBlur={() => setTouched((t) => ({ ...t, username: true }))}
              placeholder="yourhandle"
              placeholderTextColor={PALETTE.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
              accessibilityLabel="Username"
            />
            {usernameError && <Text style={styles.fieldError}>{usernameError}</Text>}
          </View>

          {/* Email */}
          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              id="sign-up-email"
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
              id="sign-up-password"
              style={[styles.input, passwordError ? styles.inputError : null]}
              value={password}
              onChangeText={setPassword}
              onBlur={() => setTouched((t) => ({ ...t, password: true }))}
              placeholder="At least 8 characters"
              placeholderTextColor={PALETTE.textMuted}
              secureTextEntry
              autoComplete="new-password"
              textContentType="newPassword"
              returnKeyType="next"
              accessibilityLabel="Password"
            />
            {passwordError && <Text style={styles.fieldError}>{passwordError}</Text>}
          </View>

          {/* Confirm Password */}
          <View style={styles.field}>
            <Text style={styles.label}>Confirm password</Text>
            <TextInput
              id="sign-up-confirm"
              style={[styles.input, confirmError ? styles.inputError : null]}
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              onBlur={() => setTouched((t) => ({ ...t, confirmPassword: true }))}
              placeholder="Repeat password"
              placeholderTextColor={PALETTE.textMuted}
              secureTextEntry
              returnKeyType="done"
              onSubmitEditing={handleSignUp}
              accessibilityLabel="Confirm password"
            />
            {confirmError && <Text style={styles.fieldError}>{confirmError}</Text>}
          </View>

          {/* Submit */}
          <Pressable
            id="sign-up-submit"
            style={({ pressed }) => [
              styles.button,
              pressed && styles.buttonPressed,
              !canSubmit && styles.buttonDisabled,
            ]}
            onPress={handleSignUp}
            disabled={!canSubmit}
            accessibilityRole="button"
            accessibilityLabel="Create account"
          >
            <Text style={styles.buttonText}>
              {isSubmitting ? 'Creating account…' : 'Create account'}
            </Text>
          </Pressable>

          {/* Sign in link */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Already have an account?{' '}</Text>
            <Link href="/auth/sign-in" asChild>
              <Pressable accessibilityRole="link">
                <Text style={styles.footerLink}>Sign in</Text>
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
  brand: {
    alignItems: 'center',
    marginBottom: 32,
  },
  logo: {
    fontFamily: 'Inter_700Bold',
    fontSize: 40,
    color: PALETTE.text,
    letterSpacing: -2,
  },
  tagline: {
    fontFamily: 'Inter_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    marginTop: 4,
  },
  card: {
    backgroundColor: PALETTE.surface,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: PALETTE.glassBorder,
    padding: 28,
    gap: 14,
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
    marginTop: -6,
  },
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
