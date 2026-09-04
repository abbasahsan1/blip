export const PALETTE = {
  // Backgrounds
  bg: '#09090b',
  surface: '#121215',
  card: '#18181b',
  cardHover: '#1c1c20',

  // Borders
  border: '#27272a',
  borderSubtle: '#1c1c1f',

  // Text
  text: '#fafafa',
  textSecondary: '#a1a1aa',
  textMuted: '#71717a',

  // Brand
  primary: '#ffffff',
  accent: '#6366f1', // indigo — audio platform feel
  accentDim: 'rgba(99, 102, 241, 0.15)',

  // State
  success: '#10b981',
  error: '#ef4444',
  errorDim: 'rgba(239, 68, 68, 0.12)',
  warning: '#f59e0b',

  // Overlays
  overlay: 'rgba(0,0,0,0.7)',
  glass: 'rgba(255,255,255,0.04)',
  glassBorder: 'rgba(255,255,255,0.08)',
} as const;

export type PaletteKey = keyof typeof PALETTE;
