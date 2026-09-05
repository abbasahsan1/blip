import { api, ApiError } from '../api';
import { useUploadStore } from '../store/uploadStore';

export interface AudioDraft {
  title: string;
  description?: string | null;
  durationSeconds: number;
}

export interface UploadAudioParams {
  file: File;
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
 * Multi-stage real direct upload pipeline:
 * 1. Presign: Request upload ticket and direct S3/B2 PUT URL.
 * 2. Direct Binary Upload: Stream raw bytes via XMLHttpRequest, binding real upload progress.
 * 3. Complete Ingest: Finalize ingest record and publish blipp in PostgreSQL.
 */
export async function uploadAudio(params: UploadAudioParams): Promise<any> {
  const { file, draft } = params;
  const uploadStore = useUploadStore.getState();

  uploadStore.reset();
  uploadStore.setIsUploading(true);
  uploadStore.setProgress(0);

  try {
    // Stage 1: Presign
    const { data } = await api.post<{
      upload_id: string;
      storage_key: string;
      presigned_url: string;
    }>('/v1/uploads/presign', {
      file_name: file.name,
      mime_type: file.type || 'audio/mpeg',
      size_bytes: file.size,
    });

    // Stage 2: Direct Binary Upload with real byte progress
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', data.presigned_url, true);
      xhr.setRequestHeader('Content-Type', file.type || 'audio/mpeg');

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          const percentage = Math.round((event.loaded / event.total) * 100);
          useUploadStore.getState().setProgress(percentage);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          useUploadStore.getState().setProgress(100);
          resolve();
        } else {
          reject(new Error(`Binary storage upload failed with status ${xhr.status}`));
        }
      };

      xhr.onerror = () => {
        reject(new Error('Network error during binary upload to object storage'));
      };

      xhr.onabort = () => {
        reject(new Error('Binary upload was aborted'));
      };

      xhr.send(file);
    });

    // Stage 3: Complete Ingest
    const res = await api.post(`/v1/uploads/${data.upload_id}/complete`, {
      title: draft.title,
      description: draft.description || null,
      duration_seconds: Math.round(draft.durationSeconds),
    });

    uploadStore.setIsUploading(false);
    return res.data;
  } catch (err: unknown) {
    uploadStore.setIsUploading(false);
    const msg =
      err instanceof ApiError
        ? err.message
        : err instanceof Error
        ? err.message
        : 'An unexpected error occurred during audio upload.';
    uploadStore.setError(msg);
    throw err;
  }
}
