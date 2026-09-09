/**
 * StoryRecordingSheet
 *
 * Ephemeral story creation sheet (§5.4).
 * Uses expo-av audio recording APIs (with Web MediaRecorder fallback).
 * Max duration: 60 seconds.
 * Provides live recording timer, preview playback, and direct upload via api.uploadStory(formData).
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  useAudioRecorder,
  createAudioPlayer,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  RecordingPresets,
  type AudioPlayer,
  type AudioStatus,
} from 'expo-audio';
import { PALETTE } from '@/lib/palette';
import { PlayMark, PauseMark } from '@/components/common/Icons';
import { api } from '@/lib/api';

interface Props {
  visible: boolean;
  onClose: () => void;
  onStoryUploaded: () => void;
}

type RecordingPhase = 'idle' | 'recording' | 'preview' | 'uploading';

function formatTimer(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function StoryRecordingSheet({
  visible,
  onClose,
  onStoryUploaded,
}: Props) {
  const [phase, setPhase] = useState<RecordingPhase>('idle');
  const [recordedSeconds, setRecordedSeconds] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Audio Recording references
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const isRecordingRef = useRef(false);
  const mediaRecorderRef = useRef<any>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordedBlobRef = useRef<Blob | null>(null);
  const recordedUriRef = useRef<string | null>(null);

  // Timer reference
  const timerIntervalRef = useRef<any>(null);

  // Preview playback references
  const [isPreviewPlaying, setIsPreviewPlaying] = useState(false);
  const previewPlayerRef = useRef<AudioPlayer | null>(null);
  const previewSubRef = useRef<{ remove: () => void } | null>(null);
  const previewWebAudioRef = useRef<HTMLAudioElement | null>(null);

  // Reset state on open/close
  useEffect(() => {
    if (!visible) {
      cleanupAll();
    } else {
      setPhase('idle');
      setRecordedSeconds(0);
      setErrorMessage(null);
    }
  }, [visible]);

  // 60-second auto-stop during recording
  useEffect(() => {
    if (phase === 'recording') {
      timerIntervalRef.current = setInterval(() => {
        setRecordedSeconds((prev) => {
          if (prev >= 59) {
            void stopRecording();
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    } else {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    }

    return () => {
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
        timerIntervalRef.current = null;
      }
    };
  }, [phase]);

  const startRecording = async () => {
    setErrorMessage(null);
    setRecordedSeconds(0);
    audioChunksRef.current = [];
    recordedBlobRef.current = null;
    recordedUriRef.current = null;

    try {
      // 1. Web Platform MediaRecorder fallback
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.mediaDevices?.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new (window as any).MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;

        mediaRecorder.ondataavailable = (e: any) => {
          if (e.data && e.data.size > 0) {
            audioChunksRef.current.push(e.data);
          }
        };

        mediaRecorder.onstop = () => {
          const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
          recordedBlobRef.current = blob;
          recordedUriRef.current = URL.createObjectURL(blob);
          stream.getTracks().forEach((track) => track.stop());
        };

        mediaRecorder.start(250);
        setPhase('recording');
        return;
      }

      // 2. Native expo-audio Recording
      const perm = await requestRecordingPermissionsAsync();
      if (!perm.granted) {
        setErrorMessage('Microphone permission is required to record a story.');
        return;
      }

      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
      }).catch(() => {});

      await recorder.prepareToRecordAsync();
      recorder.record();
      isRecordingRef.current = true;
      setPhase('recording');
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to start recording.');
      setPhase('idle');
    }
  };

  const stopRecording = async () => {
    try {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
        mediaRecorderRef.current = null;
      }

      if (isRecordingRef.current || recorder.isRecording) {
        await recorder.stop();
        isRecordingRef.current = false;
        const uri = recorder.uri;
        recordedUriRef.current = uri;
      }

      setPhase('preview');
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to finish recording.');
      setPhase('idle');
    }
  };

  const togglePreviewPlayback = async () => {
    const uri = recordedUriRef.current;
    if (!uri) return;

    if (isPreviewPlaying) {
      if (previewPlayerRef.current) {
        try {
          previewPlayerRef.current.pause();
        } catch {}
      }
      if (previewWebAudioRef.current) {
        previewWebAudioRef.current.pause();
      }
      setIsPreviewPlaying(false);
      return;
    }

    // Play preview
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const audio = new window.Audio(uri);
        previewWebAudioRef.current = audio;
        audio.onended = () => setIsPreviewPlaying(false);
        audio.onplay = () => setIsPreviewPlaying(true);
        audio.onpause = () => setIsPreviewPlaying(false);
        await audio.play();
      } else {
        cleanupPreview();
        const player = createAudioPlayer(uri);
        previewPlayerRef.current = player;
        const sub = (player as any).addListener(
          'playbackStatusUpdate',
          (status: AudioStatus) => {
            if (status.didJustFinish) {
              setIsPreviewPlaying(false);
            }
          },
        );
        previewSubRef.current = sub;
        player.play();
        setIsPreviewPlaying(true);
      }
    } catch {
      setIsPreviewPlaying(false);
    }
  };

  const resetRecording = () => {
    cleanupPreview();
    setPhase('idle');
    setRecordedSeconds(0);
    setErrorMessage(null);
  };

  const handleUploadStory = async () => {
    setPhase('uploading');
    setErrorMessage(null);

    try {
      const formData = new FormData();
      const durSec = Math.max(1, recordedSeconds);

      if (Platform.OS === 'web') {
        if (recordedBlobRef.current) {
          formData.append('file', recordedBlobRef.current, 'story.webm');
        } else if (recordedUriRef.current) {
          const res = await fetch(recordedUriRef.current);
          const blob = await res.blob();
          formData.append('file', blob, 'story.webm');
        } else {
          throw new Error('No audio data found to upload.');
        }
      } else {
        const uri = recordedUriRef.current;
        if (!uri) throw new Error('No audio file found.');
        formData.append('file', {
          uri,
          name: 'story.m4a',
          type: 'audio/m4a',
        } as any);
      }

      formData.append('duration_seconds', String(durSec));

      await api.uploadStory(formData);
      onStoryUploaded();
      onClose();
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to post story. Please try again.');
      setPhase('preview');
    }
  };

  const cleanupPreview = () => {
    if (previewSubRef.current) {
      try {
        previewSubRef.current.remove();
      } catch {}
      previewSubRef.current = null;
    }
    if (previewPlayerRef.current) {
      try {
        previewPlayerRef.current.pause();
        if (typeof (previewPlayerRef.current as any).release === 'function') {
          (previewPlayerRef.current as any).release();
        } else if (typeof (previewPlayerRef.current as any).remove === 'function') {
          (previewPlayerRef.current as any).remove();
        }
      } catch {}
      previewPlayerRef.current = null;
    }
    if (previewWebAudioRef.current) {
      previewWebAudioRef.current.pause();
      previewWebAudioRef.current.src = '';
      previewWebAudioRef.current = null;
    }
    setIsPreviewPlaying(false);
  };

  const cleanupAll = () => {
    cleanupPreview();
    if (isRecordingRef.current || recorder.isRecording) {
      recorder.stop().catch(() => {});
      isRecordingRef.current = false;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current = null;
    }
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    setPhase('idle');
    setRecordedSeconds(0);
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      onRequestClose={onClose}
    >
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.handle} />

          <Text style={styles.sheetTitle}>New 24h Audio Story</Text>
          <Text style={styles.sheetSubtitle}>
            Share an ephemeral audio broadcast with your followers (up to 60s).
          </Text>

          {errorMessage && (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{errorMessage}</Text>
            </View>
          )}

          {/* Center Stage: Interactive Recording & Preview */}
          <View style={styles.recordingStage}>
            {phase === 'idle' && (
              <View style={styles.idleContainer}>
                <Pressable
                  style={({ pressed }) => [
                    styles.recordTriggerBtn,
                    pressed && styles.recordTriggerPressed,
                  ]}
                  onPress={startRecording}
                  accessibilityRole="button"
                  accessibilityLabel="Start recording story"
                  testID="start-story-record-button"
                >
                  <View style={styles.recordInnerDot} />
                </Pressable>
                <Text style={styles.idlePrompt}>Tap to record (max 60s)</Text>
              </View>
            )}

            {phase === 'recording' && (
              <View style={styles.recordingContainer}>
                <View style={styles.pulsingRing}>
                  <Pressable
                    style={styles.stopTriggerBtn}
                    onPress={stopRecording}
                    accessibilityRole="button"
                    accessibilityLabel="Stop recording story"
                    testID="stop-story-record-button"
                  >
                    <View style={styles.stopInnerSquare} />
                  </Pressable>
                </View>

                <Text style={styles.timerDisplay}>
                  {formatTimer(recordedSeconds)} / 01:00
                </Text>
                <Text style={styles.recordingStatusText}>Recording audio...</Text>
              </View>
            )}

            {phase === 'preview' && (
              <View style={styles.previewContainer}>
                <Pressable
                  style={({ pressed }) => [
                    styles.previewPlayBtn,
                    pressed && styles.previewPlayBtnPressed,
                  ]}
                  onPress={togglePreviewPlayback}
                  accessibilityRole="button"
                  accessibilityLabel={isPreviewPlaying ? 'Pause preview' : 'Play preview'}
                  testID="preview-story-play-button"
                >
                  {isPreviewPlaying ? (
                    <PauseMark size={24} color="#ffffff" />
                  ) : (
                    <PlayMark size={24} color="#ffffff" />
                  )}
                </Pressable>

                <Text style={styles.previewDurationText}>
                  Recorded: {formatTimer(recordedSeconds)}
                </Text>

                <View style={styles.actionButtonsRow}>
                  <Pressable
                    style={styles.rerecordBtn}
                    onPress={resetRecording}
                    accessibilityRole="button"
                    accessibilityLabel="Re-record story"
                  >
                    <Text style={styles.rerecordBtnText}>Re-record</Text>
                  </Pressable>

                  <Pressable
                    style={styles.postStoryBtn}
                    onPress={handleUploadStory}
                    accessibilityRole="button"
                    accessibilityLabel="Post audio story"
                    testID="post-story-button"
                  >
                    <Text style={styles.postStoryBtnText}>Share Story</Text>
                  </Pressable>
                </View>
              </View>
            )}

            {phase === 'uploading' && (
              <View style={styles.uploadingContainer}>
                <ActivityIndicator size="large" color={PALETTE.accent} />
                <Text style={styles.uploadingText}>Publishing 24h story...</Text>
              </View>
            )}
          </View>

          <Pressable style={styles.cancelBtn} onPress={onClose}>
            <Text style={styles.cancelBtnText}>Cancel</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: PALETTE.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingTop: 12,
    paddingBottom: 40,
    paddingHorizontal: 24,
    borderTopWidth: 1,
    borderColor: PALETTE.border,
  },
  handle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: PALETTE.border,
    alignSelf: 'center',
    marginBottom: 16,
  },
  sheetTitle: {
    fontFamily: 'Sora_700Bold',
    fontSize: 20,
    color: PALETTE.text,
    textAlign: 'center',
    marginBottom: 4,
  },
  sheetSubtitle: {
    fontFamily: 'PlusJakartaSans_400Regular',
    fontSize: 13,
    color: PALETTE.textSecondary,
    textAlign: 'center',
    marginBottom: 20,
  },
  errorBox: {
    backgroundColor: 'rgba(239, 68, 68, 0.12)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.3)',
    borderRadius: 8,
    padding: 10,
    marginBottom: 16,
  },
  errorText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 12,
    color: '#ef4444',
    textAlign: 'center',
  },
  recordingStage: {
    minHeight: 190,
    justifyContent: 'center',
    alignItems: 'center',
    marginVertical: 12,
  },
  idleContainer: {
    alignItems: 'center',
    gap: 16,
  },
  recordTriggerBtn: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 4,
    borderColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
  },
  recordTriggerPressed: {
    opacity: 0.8,
    transform: [{ scale: 0.96 }],
  },
  recordInnerDot: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: PALETTE.accent,
  },
  idlePrompt: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13,
    color: PALETTE.textSecondary,
  },
  recordingContainer: {
    alignItems: 'center',
    gap: 12,
  },
  pulsingRing: {
    width: 84,
    height: 84,
    borderRadius: 42,
    borderWidth: 3,
    borderColor: '#ef4444',
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
  },
  stopTriggerBtn: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#ef4444',
    justifyContent: 'center',
    alignItems: 'center',
  },
  stopInnerSquare: {
    width: 22,
    height: 22,
    borderRadius: 4,
    backgroundColor: '#ffffff',
  },
  timerDisplay: {
    fontFamily: 'Sora_700Bold',
    fontSize: 22,
    color: PALETTE.text,
    fontVariant: ['tabular-nums'],
  },
  recordingStatusText: {
    fontFamily: 'PlusJakartaSans_500Medium',
    fontSize: 13,
    color: '#ef4444',
  },
  previewContainer: {
    alignItems: 'center',
    width: '100%',
    gap: 14,
  },
  previewPlayBtn: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: PALETTE.accent,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: PALETTE.accent,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 10,
    elevation: 6,
  },
  previewPlayBtnPressed: {
    opacity: 0.8,
  },
  previewDurationText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.textSecondary,
    fontVariant: ['tabular-nums'],
  },
  actionButtonsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    width: '100%',
    marginTop: 8,
  },
  rerecordBtn: {
    flex: 1,
    paddingVertical: 12,
    backgroundColor: PALETTE.card,
    borderRadius: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PALETTE.border,
  },
  rerecordBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.textSecondary,
  },
  postStoryBtn: {
    flex: 1,
    paddingVertical: 12,
    backgroundColor: PALETTE.accent,
    borderRadius: 10,
    alignItems: 'center',
  },
  postStoryBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: '#ffffff',
  },
  uploadingContainer: {
    alignItems: 'center',
    gap: 16,
    paddingVertical: 20,
  },
  uploadingText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.text,
  },
  cancelBtn: {
    marginTop: 12,
    paddingVertical: 12,
    alignItems: 'center',
  },
  cancelBtnText: {
    fontFamily: 'PlusJakartaSans_600SemiBold',
    fontSize: 14,
    color: PALETTE.textMuted,
  },
});
