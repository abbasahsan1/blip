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

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Trigger web file input
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

    // Determine audio duration
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
      setErrorMessage('Please provide a title for your blipp.');
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
      setSuccessMessage('Blipp uploaded successfully! Redirecting to feed...');
      // Refresh feed store so the new blipp appears immediately
      await loadFeed();
      setTimeout(() => {
        setTitle('');
        setSelectedFile(null);
        setDuration(0);
        setSuccessMessage(null);
        router.replace('/(tabs)');
      }, 1000);
    } else {
      setErrorMessage(result.error || 'Failed to upload blipp. Please try again.');
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[
        styles.contentContainer,
        { paddingTop: insets.top + 20, paddingBottom: insets.bottom + 40 },
      ]}
      keyboardShouldPersistTaps="handled"
    >
      {/* Hidden file input for web */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg"
        style={{ display: 'none' }}
      />

      {/* Header */}
      <View style={styles.header}>
        <View style={styles.iconCircle}>
          <Text style={styles.iconText}>🎙</Text>
        </View>
        <Text style={styles.heading}>Create a Blipp</Text>
        <Text style={styles.subheading}>
          Share an engaging audio clip with the community. Audio files are streamed directly.
        </Text>
      </View>

      {/* Feedback Banners */}
      {errorMessage && (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>⚠ {errorMessage}</Text>
        </View>
      )}

      {successMessage && (
        <View style={styles.successBanner}>
          <Text style={styles.successText}>✓ {successMessage}</Text>
        </View>
      )}

      {/* Form Card */}
      <View style={styles.card}>
        {/* File Picker Zone */}
        <Pressable
          style={[styles.dropzone, selectedFile ? styles.dropzoneActive : null]}
          onPress={handleSelectFileClick}
          disabled={isUploading}
        >
          <Text style={styles.dropzoneIcon}>{selectedFile ? '🎵' : '📁'}</Text>
          <Text style={styles.dropzoneTitle}>
            {selectedFile ? selectedFile.name : 'Select Audio File'}
          </Text>
          <Text style={styles.dropzoneSub}>
            {selectedFile
              ? `${(selectedFile.size / (1024 * 1024)).toFixed(2)} MB${
                  duration > 0 ? ` · ${Math.floor(duration / 60)}:${String(duration % 60).padStart(2, '0')}` : ''
                }`
              : 'MP3, WAV, M4A, or AAC (Tap to browse)'}
          </Text>
          {selectedFile && (
            <Text style={styles.changeFilePrompt}>Tap to choose a different file</Text>
          )}
        </Pressable>

        {/* Title Input */}
        <View style={styles.inputGroup}>
          <Text style={styles.label}>Title</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. Why Focus Beats Motivation"
            placeholderTextColor={PALETTE.textMuted}
            value={title}
            onChangeText={setTitle}
            editable={!isUploading}
            maxLength={100}
          />
        </View>

        {/* Upload Action Button */}
        <Pressable
          style={[styles.submitButton, isUploading ? styles.submitButtonDisabled : null]}
          onPress={handleSubmit}
          disabled={isUploading}
        >
          {isUploading ? (
            <View style={styles.buttonRow}>
              <ActivityIndicator size="small" color="#000" />
              <Text style={styles.submitButtonText}>Uploading Audio...</Text>
            </View>
          ) : (
            <Text style={styles.submitButtonText}>Publish Blipp</Text>
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
    paddingHorizontal: 20,
    alignItems: 'center',
  },
  header: {
    alignItems: 'center',
    marginBottom: 24,
    maxWidth: 480,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: PALETTE.surface,
    borderWidth: 1,
    borderColor: PALETTE.border,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  iconText: {
    fontSize: 28,
  },
  heading: {
    fontFamily: 'Inter_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    marginBottom: 8,
    textAlign: 'center',
  },
  subheading: {
    fontFamily: 'Inter_400Regular',
    fontSize: 14,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },
  errorBanner: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: 'rgba(239, 68, 68, 0.15)',
    borderWidth: 1,
    borderColor: PALETTE.error,
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  errorText: {
    color: PALETTE.error,
    fontSize: 13,
    fontFamily: 'Inter_500Medium',
  },
  successBanner: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    borderWidth: 1,
    borderColor: PALETTE.success,
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  successText: {
    color: PALETTE.success,
    fontSize: 13,
    fontFamily: 'Inter_500Medium',
  },
  card: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: PALETTE.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: PALETTE.border,
    padding: 20,
    gap: 18,
  },
  dropzone: {
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: PALETTE.border,
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255,255,255,0.02)',
  },
  dropzoneActive: {
    borderColor: PALETTE.accent,
    backgroundColor: 'rgba(37, 99, 235, 0.05)',
  },
  dropzoneIcon: {
    fontSize: 32,
    marginBottom: 8,
  },
  dropzoneTitle: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 15,
    color: PALETTE.text,
    textAlign: 'center',
    marginBottom: 4,
  },
  dropzoneSub: {
    fontFamily: 'Inter_400Regular',
    fontSize: 12,
    color: PALETTE.textMuted,
    textAlign: 'center',
  },
  changeFilePrompt: {
    fontFamily: 'Inter_500Medium',
    fontSize: 11,
    color: PALETTE.accent,
    marginTop: 8,
  },
  inputGroup: {
    gap: 6,
  },
  label: {
    fontFamily: 'Inter_500Medium',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },
  input: {
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: PALETTE.border,
    color: PALETTE.text,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 14,
    fontFamily: 'Inter_400Regular',
  },
  submitButton: {
    backgroundColor: '#ffffff',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  submitButtonDisabled: {
    opacity: 0.6,
  },
  buttonRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  submitButtonText: {
    fontFamily: 'Inter_600SemiBold',
    fontSize: 15,
    color: '#000000',
  },
});
