import { create } from 'zustand';
import type { UploadStatus } from '../types';

export interface UploadStore {
  status: UploadStatus;
  progress: number;
  isUploading: boolean;
  error: string | null;
  uploadId: string | null;
  setStatus: (status: UploadStatus) => void;
  setProgress: (percentage: number) => void;
  setIsUploading: (uploading: boolean) => void;
  setError: (error: string | null) => void;
  setUploadId: (uploadId: string | null) => void;
  reset: () => void;
}

export const useUploadStore = create<UploadStore>((set) => ({
  status: 'idle',
  progress: 0,
  isUploading: false,
  error: null,
  uploadId: null,
  setStatus: (status: UploadStatus) =>
    set({
      status,
      isUploading: ['created', 'uploading', 'processing', 'transcoding', 'copyright_check', 'moderation'].includes(status),
    }),
  setProgress: (percentage: number) =>
    set({ progress: Math.max(0, Math.min(100, Math.round(percentage))) }),
  setIsUploading: (isUploading: boolean) =>
    set({
      isUploading,
      status: isUploading ? 'uploading' : 'idle',
    }),
  setError: (error: string | null) =>
    set({
      error,
      status: error ? 'failed' : 'idle',
      isUploading: false,
    }),
  setUploadId: (uploadId: string | null) => set({ uploadId }),
  reset: () =>
    set({
      status: 'idle',
      progress: 0,
      isUploading: false,
      error: null,
      uploadId: null,
    }),
}));
