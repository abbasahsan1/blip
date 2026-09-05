import { useState, useRef } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { PALETTE } from '@/lib/palette';
import { useSessionStore } from '@/lib/store/sessionStore';
import { useFeedStore } from '@/lib/store/feedStore';
import { uploadAudioClip, getAudioDuration } from '@/lib/upload/audioUpload';
import {
  AudioReelMark,
  StatusAlertMark,
  StatusCheckMark,
} from '@/components/common/Icons';

export default function UploadScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { status, accessToken } = useSessionStore();
  const { loadFeed } = useFeedStore();

  const [title, setTitle] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number>(0);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleSelectFileClick = () => {
    setErrorMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    setSelectedFile(file);
    setErrorMessage(null);

    // Auto-fill title if empty
    if (!title) {
      const baseName = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
      setTitle(baseName);
    }

    try {
      const dur = await getAudioDuration(file);
      setDuration(dur);
    } catch {
      setDuration(0);
    }
  };

  const handleSubmit = async () => {
    if (status !== 'authenticated') {
      setErrorMessage('You must be signed in to upload audio.');
      return;
    }

    if (!selectedFile) {
      setErrorMessage('Please select an audio file first.');
      return;
    }

    if (!title.trim()) {
      setErrorMessage('Please provide a title for your audio broadcast.');
      return;
    }

    setIsUploading(true);
    setErrorMessage(null);

    const result = await uploadAudioClip({
      file: selectedFile,
      fileName: selectedFile.name,
      title: title.trim(),
      durationSeconds: duration,
      token: accessToken || undefined,
    });

    setIsUploading(false);

    if (result.success) {
      setSuccessMessage('Broadcast uploaded successfully. Directing to feed...');
      await loadFeed();
      setTimeout(() => {
        setTitle('');
        setSelectedFile(null);
        setDuration(0);
        setSuccessMessage(null);
        router.replace('/(tabs)');
      }, 900);
    } else {
      setErrorMessage(result.error || 'Failed to upload audio. Please check network connection.');
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[
        styles.contentContainer,
        { paddingTop: insets.top + 28, paddingBottom: insets.bottom + 48 },
      ]}
      keyboardShouldPersistTaps="handled"
    >
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg"
        style={{ display: 'none' }}
      />

      {/* Header: Studio Console Header */}
      <View style={styles.header}>
        <View style={styles.headerIconChassis}>
          <AudioReelMark size={28} color={PALETTE.accent} />
        </View>
        <Text style={styles.heading}>Broadcast Audio</Text>
        <Text style={styles.subheading}>
          Encode and publish uncompressed or compressed audio directly to the community stream.
        </Text>
      </View>

      {/* Structured Feedback Banners with bespoke status marks */}
      {errorMessage && (
        <View style={styles.errorBanner} accessibilityRole="alert">
          <StatusAlertMark size={16} color={PALETTE.error} />
          <Text style={styles.errorText}>{errorMessage}</Text>
        </View>
      )}

      {successMessage && (
        <View style={styles.successBanner} accessibilityRole="alert">
          <StatusCheckMark size={16} color={PALETTE.success} />
          <Text style={styles.successText}>{successMessage}</Text>
        </View>
      )}

      {/* Console Intake Chassis Card */}
      <View style={styles.card}>
        {/* Audio Intake Dropzone */}
        <Pressable
          style={[
            styles.dropzone,
            selectedFile ? styles.dropzoneActive : null,
          ]}
          onPress={handleSelectFileClick}
          disabled={isUploading}
          accessibilityRole="button"
          accessibilityLabel={selectedFile ? `Selected: ${selectedFile.name}` : 'Select audio file'}
        >
          <View style={styles.dropzoneIconWrap}>
            <AudioReelMark
              size={36}
              color={selectedFile ? PALETTE.accent : PALETTE.textMuted}
            />
          </View>
          <Text style={styles.dropzoneTitle}>
            {selectedFile ? selectedFile.name : 'Select Audio Track'}
          </Text>
          <Text style={styles.dropzoneSub}>
            {selectedFile
              ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB${
                  duration > 0
                    ? ` • ${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}`
                    : ''
                }`
              : 'MP3, WAV, M4A, or AAC formats supported'}
          </Text>
          {selectedFile && (
            <Text style={styles.changeFilePrompt}>Select a different file</Text>
          )}
        </Pressable>

        {/* Title Input Field */}
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Broadcast Title</Text>
          <TextInput
            style={[styles.input, isFocused && styles.inputFocused]}
            placeholder="e.g. Field Recordings from the North Ridge"
            placeholderTextColor={PALETTE.textMuted}
            value={title}
            onChangeText={setTitle}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            editable={!isUploading}
            maxLength={100}
            accessibilityLabel="Broadcast Title"
          />
        </View>

        {/* Action Button */}
        <Pressable
          style={({ pressed }) => [
            styles.submitButton,
            pressed && styles.submitButtonPressed,
            isUploading ? styles.submitButtonDisabled : null,
          ]}
          onPress={handleSubmit}
          disabled={isUploading}
          accessibilityRole="button"
          accessibilityLabel="Publish Broadcast"
        >
          {isUploading ? (
            <View style={styles.buttonRow}>
              <ActivityIndicator size="small" color="#09090b" />
              <Text style={styles.submitButtonText}>Encoding & Publishing...</Text>
            </View>
          ) : (
            <Text style={styles.submitButtonText}>Publish Broadcast</Text>
          )}
        </Pressable>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: PALETTE.bg,
  },
  contentContainer: {
    paddingHorizontal: 24,
    alignItems: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 24,
    maxWidth: 460,
  },
  headerIconChassis: {
    width: 56,
    height: 56,
    borderRadius: 10,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  heading: {
    fontFamily: 'Sora_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    marginBottom: 8,
    textAlign: 'center',
    letterSpacing: -0.5,
  },
  subheading: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    maxWidth: 380,
  },
  errorBanner: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: PALETTE.errorDim,
    borderWidth: 1,
    borderColor: `${PALETTE.error}40`,
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 14,
    marginBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  errorText: {
    color: PALETTE.error,
    fontSize: 13,
    fontFamily: 'PlusJakartaSans_500Medium',
    flex: 1,
  },
  successBanner: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: 'rgba(16, 185, 129, 0.12)',
    borderWidth: 1,
    borderColor: `${PALETTE.success}40`,
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 14,
    marginBottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  successText: {
    color: PALETTE.success,
    fontSize: 13,
    fontFamily: 'PlusJakartaSans_500Medium',
    flex: 1,
  },
  card: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: PALETTE.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: PALETTE.border,
    padding: 24,
    gap: 20,
  },
  dropzone: {
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: PALETTE.border,
    borderRadius: 10,
    padding: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: PALETTE.card,
  },
  dropzoneActive: {
    borderColor: PALETTE.accent,
    borderStyle: 'solid',
    backgroundColor: PALETTE.accentDim,
  },
  dropzoneIconWrap: {
    marginBottom: 10,
  },
  dropzoneTitle: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 15,
    color: PALETTE.text,
    textAlign: 'center',
    marginBottom: 4,
  },
  dropzoneSub: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textMuted,
    textAlign: 'center',
  },
  changeFilePrompt: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: PALETTE.accent,
    marginTop: 10,
  },
  inputGroup: {
    gap: 6,
  },
  label: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },
  input: {
    backgroundColor: PALETTE.card,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: PALETTE.border,
    color: PALETTE.text,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    fontFamily: 'PlusJakartaSans_400Regular',
    minHeight: 46,
  },
  inputFocused: {
    borderColor: PALETTE.accent,
  },
  submitButton: {
    backgroundColor: '#ffffff',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 48,
  },
  submitButtonPressed: {
    opacity: 0.88,
  },
  submitButtonDisabled: {
    opacity: 0.5,
  },
  buttonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  submitButtonText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#09090b',
  },
});
