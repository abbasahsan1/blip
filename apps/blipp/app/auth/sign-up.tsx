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
import { StatusAlertMark } from '@/components/common/Icons';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function SignUpScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [focusedField, setFocusedField] = useState<string | null>(null);
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
      ? 'Handle must contain at least 3 characters'
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
          { paddingTop: insets.top + 32, paddingBottom: insets.bottom + 32 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Brand Console Header */}
        <View style={styles.brand}>
          <Text style={styles.logo}>blipp</Text>
          <Text style={styles.tagline}>Acoustic broadcast console</Text>
        </View>

        {/* Chassis Card */}
        <View style={styles.card}>
          <Text style={styles.heading}>Register Operator</Text>
          <Text style={styles.subheading}>Establish your broadcast handle and audio telemetry</Text>

          {authError && (
            <View style={styles.errorBanner} accessibilityRole="alert">
              <StatusAlertMark size={16} color={PALETTE.error} />
              <Text style={styles.errorBannerText}>{authError}</Text>
            </View>
          )}

          {/* Username */}
          <View style={styles.field}>
            <Text style={styles.label}>Operator Handle</Text>
            <TextInput
              id="sign-up-username"
              style={[
                styles.input,
                focusedField === 'username' && styles.inputFocused,
                usernameError ? styles.inputError : null,
              ]}
              value={username}
              onChangeText={setUsername}
              onFocus={() => setFocusedField('username')}
              onBlur={() => {
                setFocusedField(null);
                setTouched((t) => ({ ...t, username: true }));
              }}
              placeholder="handle"
              placeholderTextColor={PALETTE.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
              accessibilityLabel="Operator Handle"
            />
            {usernameError && <Text style={styles.fieldError}>{usernameError}</Text>}
          </View>

          {/* Email */}
          <View style={styles.field}>
            <Text style={styles.label}>Email Address</Text>
            <TextInput
              id="sign-up-email"
              style={[
                styles.input,
                focusedField === 'email' && styles.inputFocused,
                emailError ? styles.inputError : null,
              ]}
              value={email}
              onChangeText={setEmail}
              onFocus={() => setFocusedField('email')}
              onBlur={() => {
                setFocusedField(null);
                setTouched((t) => ({ ...t, email: true }));
              }}
              placeholder="operator@domain.com"
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
            <Text style={styles.label}>Security Key (Password)</Text>
            <TextInput
              id="sign-up-password"
              style={[
                styles.input,
                focusedField === 'password' && styles.inputFocused,
                passwordError ? styles.inputError : null,
              ]}
              value={password}
              onChangeText={setPassword}
              onFocus={() => setFocusedField('password')}
              onBlur={() => {
                setFocusedField(null);
                setTouched((t) => ({ ...t, password: true }));
              }}
              placeholder="At least 8 characters"
              placeholderTextColor={PALETTE.textMuted}
              secureTextEntry
              autoComplete="new-password"
              textContentType="newPassword"
              returnKeyType="next"
              accessibilityLabel="Security password"
            />
            {passwordError && <Text style={styles.fieldError}>{passwordError}</Text>}
          </View>

          {/* Confirm Password */}
          <View style={styles.field}>
            <Text style={styles.label}>Confirm Security Key</Text>
            <TextInput
              id="sign-up-confirm"
              style={[
                styles.input,
                focusedField === 'confirm' && styles.inputFocused,
                confirmError ? styles.inputError : null,
              ]}
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              onFocus={() => setFocusedField('confirm')}
              onBlur={() => {
                setFocusedField(null);
                setTouched((t) => ({ ...t, confirmPassword: true }));
              }}
              placeholder="Re-enter password"
              placeholderTextColor={PALETTE.textMuted}
              secureTextEntry
              returnKeyType="done"
              onSubmitEditing={handleSignUp}
              accessibilityLabel="Confirm security password"
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
            accessibilityLabel="Create operator account"
          >
            <Text style={styles.buttonText}>
              {isSubmitting ? 'Registering...' : 'Create Account'}
            </Text>
          </Pressable>

          {/* Sign in link */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Already registered? </Text>
            <Link href="/auth/sign-in" asChild>
              <Pressable accessibilityRole="link">
                <Text style={styles.footerLink}>Sign in</Text>
              </Pressable>
            </Link>
          </View>

          {/* Legal Compliance Surface */}
          <View style={styles.legalFooter}>
            <Text style={styles.legalText}>
              By creating an account, you agree to the Blipp Terms of Service and Privacy Policy.
            </Text>
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
    maxWidth: 460,
    width: '100%',
    alignSelf: 'center',
  },
  brand: {
    alignItems: 'center',
    marginBottom: 28,
  },
  logo: {
    fontFamily: 'Sora_700Bold',
    fontSize: 38,
    color: PALETTE.text,
    letterSpacing: -1.5,
  },
  tagline: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textMuted,
    marginTop: 4,
  },
  card: {
    backgroundColor: PALETTE.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    padding: 24,
    gap: 16,
  },
  heading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 20,
    color: PALETTE.text,
    letterSpacing: -0.3,
  },
  subheading: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    marginTop: -8,
  },
  errorBanner: {
    backgroundColor: PALETTE.errorDim,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: `${PALETTE.error}40`,
    paddingVertical: 10,
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  errorBannerText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13,
    color: PALETTE.error,
    flex: 1,
  },
  field: {
    gap: 6,
  },
  label: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },
  input: {
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.text,
    minHeight: 46,
  },
  inputFocused: {
    borderColor: PALETTE.accent,
  },
  inputError: {
    borderColor: PALETTE.error,
  },
  fieldError: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.error,
  },
  button: {
    backgroundColor: PALETTE.accent,
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
    minHeight: 48,
  },
  buttonPressed: {
    opacity: 0.88,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#ffffff',
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 4,
  },
  footerText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
  },
  footerLink: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.accent,
  },
  legalFooter: {
    borderTopWidth: 1,
    borderTopColor: PALETTE.borderSubtle,
    paddingTop: 12,
    marginTop: 4,
  },
  legalText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 11,
    color: PALETTE.textMuted,
    textAlign: 'center',
    lineHeight: 16,
  },
});
