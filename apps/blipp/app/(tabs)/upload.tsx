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
import { useUploadStore } from '@/lib/store/uploadStore';
import { uploadAudio, getAudioDuration } from '@/lib/upload/audioUpload';
import {
  AudioReelMark,
  StatusAlertMark,
  StatusCheckMark,
} from '@/components/common/Icons';

export default function UploadScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { status } = useSessionStore();
  const { refreshFeed } = useFeedStore();
  const {
    status: uploadStatus,
    progress,
    isUploading,
    error: storeError,
    reset: resetUploadStore,
  } = useUploadStore();

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [duration, setDuration] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [isDescFocused, setIsDescFocused] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleSelectFileClick = () => {
    setErrorMessage(null);
    resetUploadStore();
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
    resetUploadStore();

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
      setErrorMessage('Please provide a title for your audio blipp.');
      return;
    }

    setErrorMessage(null);

    try {
      await uploadAudio({
        file: selectedFile,
        draft: {
          title: title.trim(),
          description: description.trim() || null,
          durationSeconds: duration,
        },
      });

      setSuccessMessage('Published successfully!');
      await refreshFeed();
      setTimeout(() => {
        setTitle('');
        setDescription('');
        setSelectedFile(null);
        setDuration(0);
        setSuccessMessage(null);
        resetUploadStore();
        router.replace('/(tabs)');
      }, 1000);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Failed to upload audio. Please check your network connection.';
      setErrorMessage(msg);
    }
  };

  const displayError = errorMessage || storeError;

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
        data-testid="audio-file-input"
        id="audio-file-input"
      />

      {/* Header: Studio Console Header */}
      <View style={styles.header}>
        <View style={styles.headerIconChassis}>
          <AudioReelMark size={28} color={PALETTE.accent} />
        </View>
        <Text style={styles.heading}>Post Blipp</Text>
        <Text style={styles.subheading}>
          Upload and auto-transcode high quality audio reels with multi-bitrate streaming variants.
        </Text>
      </View>

      {/* Structured Feedback Banners with bespoke status marks */}
      {displayError && (
        <View style={styles.errorBanner} accessibilityRole="alert" testID="upload-error-banner">
          <StatusAlertMark size={16} color={PALETTE.error} />
          <View style={{ flex: 1 }}>
            <Text style={styles.errorText}>{displayError}</Text>
          </View>
          <Pressable
            style={styles.inlineRetryButton}
            onPress={handleSubmit}
            accessibilityRole="button"
            accessibilityLabel="Retry Upload"
          >
            <Text style={styles.inlineRetryButtonText}>Retry</Text>
          </Pressable>
        </View>
      )}

      {successMessage && (
        <View style={styles.successBanner} accessibilityRole="alert" testID="upload-success-banner">
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
          testID="audio-dropzone"
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
          {selectedFile && !isUploading && (
            <Text style={styles.changeFilePrompt}>Select a different file</Text>
          )}
        </Pressable>

        {/* Title Input Field */}
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Blipp Title</Text>
          <TextInput
            style={[styles.input, isFocused && styles.inputFocused]}
            placeholder="e.g. Morning Reflections Episode 4"
            placeholderTextColor={PALETTE.textMuted}
            value={title}
            onChangeText={setTitle}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            editable={!isUploading}
            maxLength={100}
            accessibilityLabel="Blipp Title"
            testID="blipp-title-input"
          />
        </View>

        {/* Description Input Field */}
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Description (Optional)</Text>
          <TextInput
            style={[styles.input, styles.textArea, isDescFocused && styles.inputFocused]}
            placeholder="Tell your listeners about this blipp..."
            placeholderTextColor={PALETTE.textMuted}
            value={description}
            onChangeText={setDescription}
            onFocus={() => setIsDescFocused(true)}
            onBlur={() => setIsDescFocused(false)}
            editable={!isUploading}
            multiline
            numberOfLines={3}
            maxLength={500}
            accessibilityLabel="Blipp Description"
            testID="blipp-description-input"
          />
        </View>

        {/* Dynamic Multi-Stage Processing Indicator */}
        {isUploading && (
          <View style={styles.progressSection} testID="upload-progress-section">
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${progress}%` }]} testID="upload-progress-bar" />
            </View>
            <View style={styles.progressInfo}>
              <Text style={styles.progressText} testID="upload-status-text">
                {uploadStatus === 'transcoding'
                  ? 'Transcoding audio variants...'
                  : uploadStatus === 'completed'
                  ? 'Published successfully!'
                  : `Uploading audio... (${progress}%)`}
              </Text>
              <Text style={styles.progressPercentage}>{progress}%</Text>
            </View>
          </View>
        )}

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
          accessibilityLabel="Post Blipp"
          testID="post-blipp-button"
        >
          {isUploading ? (
            <View style={styles.buttonRow}>
              <ActivityIndicator size="small" color="#09090b" />
              <Text style={styles.submitButtonText}>
                {uploadStatus === 'transcoding'
                  ? 'Transcoding audio variants...'
                  : 'Uploading audio...'}
              </Text>
            </View>
          ) : uploadStatus === 'failed' ? (
            <Text style={styles.submitButtonText}>Retry Post</Text>
          ) : (
            <Text style={styles.submitButtonText}>Post Blipp</Text>
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
  inlineRetryButton: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    borderRadius: 6,
    borderWidth: 1,
    borderColor: `${PALETTE.error}60`,
  },
  inlineRetryButtonText: {
    color: PALETTE.error,
    fontSize: 12,
    fontFamily: 'PlusJakartaSans_600SemiBold',
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
  textArea: {
    minHeight: 80,
    textAlignVertical: 'top',
    paddingTop: 12,
  },
  progressSection: {
    gap: 8,
  },
  progressTrack: {
    height: 6,
    backgroundColor: PALETTE.card,
    borderRadius: 3,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  progressFill: {
    height: '100%',
    backgroundColor: PALETTE.accent,
    borderRadius: 2,
  },
  progressInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  progressText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: PALETTE.textSecondary,
  },
  progressPercentage: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 12,
    color: PALETTE.accent,
    fontVariant: ['tabular-nums'],
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
