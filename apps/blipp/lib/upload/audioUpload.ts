import { ApiError, blippApi, type BlippUploadResponse } from '../api';

export interface UploadAudioParams {
  file: File | Blob;
  fileName?: string;
  title: string;
  durationSeconds?: number;
  token?: string;
}

export interface UploadAudioResult {
  success: boolean;
  blipp?: BlippUploadResponse;
  error?: string;
  code?: string;
}

/**
 * Calculates audio duration from a File/Blob using the browser Audio API.
 */
export async function getAudioDuration(file: File | Blob): Promise<number> {
  return new Promise((resolve) => {
    if (typeof window === 'undefined' || typeof Audio === 'undefined') {
      return resolve(0);
    }
    try {
      const objectUrl = URL.createObjectURL(file);
      const audio = new Audio(objectUrl);
      audio.addEventListener('loadedmetadata', () => {
        const dur = Math.round(audio.duration) || 0;
        URL.revokeObjectURL(objectUrl);
        resolve(dur);
      });
      audio.addEventListener('error', () => {
        URL.revokeObjectURL(objectUrl);
        resolve(0);
      });
    } catch {
      resolve(0);
    }
  });
}

/**
 * Uploads an audio clip to POST /v1/blipps/upload with multipart form data.
 */
export async function uploadAudioClip(params: UploadAudioParams): Promise<UploadAudioResult> {
  const { file, fileName, title, durationSeconds = 0, token } = params;

  if (!file) {
    return { success: false, error: 'Please select an audio file to upload.' };
  }

  if (!title.trim()) {
    return { success: false, error: 'Please provide a title for your blipp.' };
  }

  const formData = new FormData();
  const resolvedName = fileName || (file instanceof File ? file.name : 'audio.mp3');
  formData.append('file', file, resolvedName);
  formData.append('title', title.trim());
  formData.append('duration_seconds', String(Math.max(0, Math.round(durationSeconds))));

  try {
    const blipp = await blippApi.uploadBlipp(formData, token);
    return { success: true, blipp };
  } catch (err) {
    if (err instanceof ApiError) {
      return {
        success: false,
        error: err.message || 'Upload failed. Please try again.',
        code: err.code,
      };
    }
    return {
      success: false,
      error: err instanceof Error ? err.message : 'An unexpected error occurred during upload.',
    };
  }
}
