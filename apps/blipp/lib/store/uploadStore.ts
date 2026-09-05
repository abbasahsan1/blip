import { create } from 'zustand';

export interface UploadStore {
  progress: number;
  isUploading: boolean;
  error: string | null;
  setProgress: (percentage: number) => void;
  setIsUploading: (uploading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useUploadStore = create<UploadStore>((set) => ({
  progress: 0,
  isUploading: false,
  error: null,
  setProgress: (percentage: number) =>
    set({ progress: Math.max(0, Math.min(100, Math.round(percentage))) }),
  setIsUploading: (isUploading: boolean) => set({ isUploading }),
  setError: (error: string | null) => set({ error, isUploading: false }),
  reset: () => set({ progress: 0, isUploading: false, error: null }),
}));
