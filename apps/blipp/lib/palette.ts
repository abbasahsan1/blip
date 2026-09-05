export const PALETTE = {
  // Studio Console Backgrounds
  bg: '#09090b', // Charcoal Vinyl base
  surface: '#121215', // Deck Console housing
  card: '#18181b', // Module chassis
  cardHover: '#1f1f24',

  // Mechanical Borders
  border: '#27272a', // Track groove border
  borderSubtle: '#1c1c1f',

  // Readout Typography
  text: '#fafafa', // Signal High
  textSecondary: '#a1a1aa', // Studio Readout
  textMuted: '#71717a', // Acoustic Low

  // Frequency Brand Accent
  primary: '#ffffff',
  accent: '#6366f1', // Resonance Violet: audio frequency needle
  accentDim: 'rgba(99, 102, 241, 0.15)',

  // Status Indicators
  success: '#10b981',
  error: '#ef4444',
  errorDim: 'rgba(239, 68, 68, 0.12)',
  warning: '#f59e0b',

  // Console Overlays (replacing liquid glass)
  overlay: 'rgba(9, 9, 11, 0.85)',
  glass: '#16161a', // Solid console inset, eliminating frosted glass
  glassBorder: '#27272a',
} as const;

export type PaletteKey = keyof typeof PALETTE;

