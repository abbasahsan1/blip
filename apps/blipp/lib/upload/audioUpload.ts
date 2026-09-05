import { Platform } from 'react-native';
import * as FileSystem from 'expo-file-system';
import { api, ApiError } from '../api';
import { useUploadStore } from '../store/uploadStore';

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
 * Cross-platform multi-stage real direct upload pipeline (Expo Web & Native):
 * 1. Presign: Request upload ticket, storage key, presigned PUT URL, and normalized content_type.
 * 2. Direct Binary Upload:
 *    - Web: XMLHttpRequest streaming binary Blob with upload.onprogress
 *    - Native: expo-file-system createUploadTask with BINARY_CONTENT
 * 3. Complete Ingest: Finalize ingest record and publish blipp in PostgreSQL.
 */
export async function uploadAudio(params: UploadAudioParams): Promise<any> {
  const { file, draft } = params;
  const uploadStore = useUploadStore.getState();

  uploadStore.reset();
  uploadStore.setIsUploading(true);
  uploadStore.setProgress(0);

  const anyFile = file as any;
  const fileName = anyFile?.name || anyFile?.fileName || anyFile?.file?.name || 'audio.mp3';
  const fileSize = anyFile?.size || anyFile?.file?.size || 0;
  const mimeType = anyFile?.type || anyFile?.file?.type || 'audio/mpeg';
  const fileUri = anyFile?.uri || '';
  const webBlob = anyFile?.file || (file instanceof Blob ? file : null);

  try {
    // Stage 1: Presign & retrieve exact content_type to prevent S3 signature mismatch
    const { data } = await api.post<{
      upload_id: string;
      storage_key: string;
      presigned_url: string;
      content_type: string;
    }>('/v1/uploads/presign', {
      file_name: fileName,
      mime_type: mimeType,
      size_bytes: fileSize,
    });

    const presigned_url = data.presigned_url;
    const content_type = data.content_type || 'audio/mpeg';

    // Stage 2: Cross-platform Direct Binary Upload
    if (Platform.OS === 'web') {
      // Standard XHR with Blob for web progress tracking
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', presigned_url);
      xhr.setRequestHeader('Content-Type', content_type);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && e.total > 0) {
          useUploadStore.getState().setProgress(Math.round((e.loaded / e.total) * 100));
        }
      };

      await new Promise((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            useUploadStore.getState().setProgress(100);
            resolve(xhr.response);
          } else {
            reject(new Error(`Upload failed with status ${xhr.status}`));
          }
        };
        xhr.onerror = () => reject(new Error('Upload network error'));
        xhr.onabort = () => reject(new Error('Upload aborted'));
        xhr.send(webBlob || anyFile);
      });
    } else {
      // Native Expo FileSystem upload
      const uploadTask = FileSystem.createUploadTask(
        presigned_url,
        fileUri,
        {
          httpMethod: 'PUT',
          headers: { 'Content-Type': content_type },
          uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
        },
        (progressData) => {
          if (progressData.totalBytesExpectedToSend > 0) {
            const percent = Math.round(
              (progressData.totalBytesSent / progressData.totalBytesExpectedToSend) * 100
            );
            useUploadStore.getState().setProgress(percent);
          }
        }
      );

      const result = await uploadTask.uploadAsync();
      if (!result || result.status < 200 || result.status >= 300) {
        throw new Error(`Native upload failed with status ${result?.status}`);
      }
      useUploadStore.getState().setProgress(100);
    }

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
