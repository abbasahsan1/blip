import { Platform } from 'react-native';
import { uploadApi, ApiError, type UploadStatusResponse } from '../api';
import { useUploadStore } from '../store/uploadStore';
import { useSessionStore } from '../store/sessionStore';

export interface AudioDraft {
  title: string;
  description?: string | null;
  durationSeconds: number;
}

export type UploadableFile =
  | File
  | { file?: File; uri: string; name?: string; size?: number; type?: string; fileName?: string };

export interface UploadAudioParams {
  file: UploadableFile;
  draft: AudioDraft;
}

export interface UploadResult {
  success: boolean;
  data?: any;
  error?: string;
}

/**
 * Calculates audio duration from an audio File/Blob using the Web Audio API,
 * strictly avoiding any URL.createObjectURL calls.
 */
export async function getAudioDuration(file: File | Blob): Promise<number> {
  if (typeof window === 'undefined') return 0;
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (AudioCtx) {
      const ctx = new AudioCtx();
      const arrayBuffer = await file.arrayBuffer();
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      const duration = Math.round(audioBuffer.duration) || 0;
      await ctx.close();
      return duration;
    }
  } catch {
    // Non-blocking duration fallback
  }
  return 0;
}

/**
 * Polls GET /v1/uploads/{uploadId} every intervalMs until processing_status is 'done' or 'failed'.
 */
export async function pollUploadStatus(
  uploadId: string,
  intervalMs = 2000,
  maxAttempts = 30,
): Promise<UploadStatusResponse> {
  let attempts = 0;
  while (attempts < maxAttempts) {
    attempts += 1;
    try {
      const statusRes = await uploadApi.getStatus(uploadId);
      const currentStatus = statusRes.processing_status;

      // Note: We deliberately only inspect processing_status and avoid any GET fetch on raw_file_url
      if (currentStatus === 'done') {
        return statusRes;
      }

      if (currentStatus === 'failed') {
        throw new Error(`Upload processing failed on the server for upload ${uploadId}.`);
      }

      // Live processing/transcoding state
      useUploadStore.getState().setStatus('transcoding');
    } catch (err: unknown) {
      if (err instanceof Error && err.message.includes('failed on the server')) {
        throw err;
      }
      // Network or non-terminal error while polling, continue until maxAttempts
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error(`Upload processing timed out after ${maxAttempts * (intervalMs / 1000)} seconds.`);
}

/**
 * Real authenticated asynchronous multipart upload pipeline (Expo Web & Native):
 * 1. Prepares multipart FormData with file, upload_type="audio", title, description.
 * 2. Injects Keycloak Bearer token from sessionStore.
 * 3. POST /v1/uploads returns 202 Accepted with upload_id.
 * 4. Polls GET /v1/uploads/{upload_id} until status is 'done' or 'failed'.
 */
export async function uploadAudio(params: UploadAudioParams): Promise<UploadStatusResponse> {
  const { file, draft } = params;
  const uploadStore = useUploadStore.getState();

  uploadStore.reset();
  uploadStore.setStatus('uploading');
  uploadStore.setProgress(15);

  const anyFile = file as any;
  const fileName = anyFile?.name || anyFile?.fileName || anyFile?.file?.name || 'audio.mp3';
  const mimeType = anyFile?.type || anyFile?.file?.type || 'audio/mpeg';
  const fileUri = anyFile?.uri || '';
  const webBlob = anyFile?.file || (file instanceof Blob ? file : null);

  const sessionToken =
    useSessionStore.getState().tokens?.accessToken || useSessionStore.getState().accessToken;

  if (!sessionToken) {
    const err = new Error('You must be signed in to upload audio.');
    uploadStore.setError(err.message);
    throw err;
  }

  try {
    const formData = new FormData();

    if (Platform.OS === 'web') {
      let blobToSend: Blob | null = null;
      if (file instanceof Blob || file instanceof File) {
        blobToSend = file;
      } else if (webBlob instanceof Blob) {
        blobToSend = webBlob;
      } else if (fileUri) {
        try {
          const resp = await fetch(fileUri);
          blobToSend = await resp.blob();
        } catch (fetchErr) {
          console.warn('Failed to fetch file URI into Blob on Web:', fetchErr);
        }
      }

      if (blobToSend) {
        formData.append('file', blobToSend, fileName);
      } else {
        throw new Error('Could not convert audio file to a binary Blob for web upload.');
      }
    } else {
      // Mobile (iOS/Android): Retain { uri, name, type } notation
      formData.append('file', {
        uri: fileUri,
        name: fileName,
        type: mimeType,
      } as any);
    }

    formData.append('upload_type', 'audio');
    formData.append('title', draft.title);
    if (draft.description) {
      formData.append('description', draft.description);
    }

    uploadStore.setProgress(40);

    // 1. Authenticated multipart POST /v1/uploads via central api client
    const uploadRes = await uploadApi.upload(formData);
    const uploadId = uploadRes.upload_id;
    uploadStore.setUploadId(uploadId);
    uploadStore.setProgress(60);

    // 2. Poll status until transcoding is finished
    uploadStore.setStatus('transcoding');
    uploadStore.setProgress(75);

    const completed = await pollUploadStatus(uploadId);
    uploadStore.setProgress(100);
    uploadStore.setStatus('completed');

    return completed;
  } catch (err: unknown) {
    let msg = 'An unexpected error occurred during audio upload.';
    if (err instanceof ApiError) {
      msg = `Upload failed (${err.status}): ${err.message}`;
    } else if (err instanceof Error) {
      msg = err.message;
    }
    uploadStore.setError(msg);
    throw new Error(msg);
  }

}
