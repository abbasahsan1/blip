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
import { GoogleSignInButton } from '@/components/auth/GoogleSignInButton';
import { StatusAlertMark } from '@/components/common/Icons';

export default function SignInScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState({ identifier: false, password: false });
  const [focusedField, setFocusedField] = useState<'identifier' | 'password' | null>(null);

  const isSubmitting = useSessionStore((s) => s.isSubmitting);
  const error = useSessionStore((s) => s.error);
  const status = useSessionStore((s) => s.status);
  const signInWithEmail = useSessionStore((s) => s.signInWithEmail);
  const signInWithOAuth = useSessionStore((s) => s.signInWithOAuth);
  const clearError = useSessionStore((s) => s.clearError);

  useEffect(() => {
    if (status === 'authenticated') {
      router.replace('/(tabs)');
    }
  }, [status, router]);

  useEffect(() => {
    clearError();
  }, [clearError]);

  const identifierError =
    touched.identifier && identifier.trim().length === 0
      ? 'Enter your username or email'
      : null;
  const passwordError =
    touched.password && password.length === 0 ? 'Enter your password' : null;
  const authError = error?.message || null;

  const canSubmit = identifier.trim().length > 0 && password.length > 0 && !isSubmitting;

  async function handleSignIn() {
    setTouched({ identifier: true, password: true });
    if (!canSubmit) return;
    await signInWithEmail(identifier.trim(), password);
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
          { paddingTop: insets.top + 40, paddingBottom: insets.bottom + 32 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {/* Brand Console Identity */}
        <View style={styles.brand}>
          <Text style={styles.logo}>blipp</Text>
          <Text style={styles.tagline}>Acoustic broadcast console</Text>
        </View>

        {/* Chassis Form Card */}
        <View style={styles.card}>
          <Text style={styles.heading}>Operator Sign In</Text>
          <Text style={styles.subheading}>Access your studio and stream telemetry</Text>

          {/* Error Banner */}
          {authError && (
            <View style={styles.errorBanner} accessibilityRole="alert">
              <StatusAlertMark size={16} color={PALETTE.error} />
              <Text style={styles.errorBannerText}>{authError}</Text>
            </View>
          )}

          {/* Identifier Input */}
          <View style={styles.field}>
            <Text style={styles.label}>Username or Email</Text>
            <TextInput
              id="sign-in-email"
              style={[
                styles.input,
                focusedField === 'identifier' && styles.inputFocused,
                identifierError ? styles.inputError : null,
              ]}
              value={identifier}
              onChangeText={setIdentifier}
              onFocus={() => setFocusedField('identifier')}
              onBlur={() => {
                setFocusedField(null);
                setTouched((t) => ({ ...t, identifier: true }));
              }}
              placeholder="operator or operator@blipp.local"
              placeholderTextColor={PALETTE.textMuted}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
              accessibilityLabel="Username or email address"
            />
            {identifierError && <Text style={styles.fieldError}>{identifierError}</Text>}
          </View>

          {/* Password Input */}
          <View style={styles.field}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              id="sign-in-password"
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
              placeholder="••••••••"
              placeholderTextColor={PALETTE.textMuted}
              secureTextEntry
              returnKeyType="done"
              onSubmitEditing={handleSignIn}
              accessibilityLabel="Password"
            />
            {passwordError && <Text style={styles.fieldError}>{passwordError}</Text>}
          </View>

          {/* Primary Action Button */}
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
            accessibilityLabel="Sign In"
          >
            <Text style={styles.buttonText}>
              {isSubmitting ? 'Authenticating...' : 'Sign In'}
            </Text>
          </Pressable>

          {/* Divider */}
          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or continue via provider</Text>
            <View style={styles.dividerLine} />
          </View>

          {/* Federated Provider Row */}
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
              <Text style={styles.appleButtonText}>Continue with Apple</Text>
            </Pressable>
          </View>

          {/* Account Creation Link */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>New operator? </Text>
            <Link href="/auth/sign-up" asChild>
              <Pressable accessibilityRole="link">
                <Text style={styles.footerLink}>Create account</Text>
              </Pressable>
            </Link>
          </View>

          {/* Legal Compliance Footer (Required Surface) */}
          <View style={styles.legalFooter}>
            <Text style={styles.legalText}>
              By proceeding, you agree to our Terms of Service and Privacy Policy.
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
    marginBottom: 32,
  },
  logo: {
    fontFamily: 'Sora_700Bold',
    fontSize: 42,
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
  oauthRow: {
    flexDirection: 'column',
    gap: 10,
  },
  appleButton: {
    backgroundColor: PALETTE.card,
    borderWidth: 1,
    borderColor: PALETTE.border,
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  appleButtonText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  divider: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginVertical: 4,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: PALETTE.border,
  },
  dividerText: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
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
