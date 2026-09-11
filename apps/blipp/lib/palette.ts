export const PALETTE = {
  // Deep Obsidian Canvas & Surfaces (Tactile Audio-First Experience)
  bg: '#0B0F19', // Deep Obsidian canvas
  surface: '#1E2638', // Surface Slate
  surfaceSubtle: '#1E1E1E',
  card: '#1E2638', // Elevated dark module chassis
  cardHover: '#2D3748',
  cardGlass: 'rgba(30, 38, 56, 0.85)',

  // Mechanical / Neon Borders
  border: '#2D3748', // Dark slate groove border
  borderSubtle: '#1E2638',
  borderNeon: '#EA580C',
  borderGlass: 'rgba(234, 88, 12, 0.25)',

  // High-Contrast Readout Typography
  text: '#F9FAFB', // Pure White signal
  textSecondary: '#9CA3AF', // Muted Silver readout
  textMuted: '#6B7280', // Muted Slate acoustic low
  primary: '#EA580C',

  // Expressive Social & Frequency Accents
  accent: '#EA580C', // Accent Orange
  accentDim: 'rgba(234, 88, 12, 0.18)',
  accentGlow: 'rgba(234, 88, 12, 0.35)',

  // Expressive Vibrant Tints
  magenta: '#F43F5E', // Electric Magenta (Bouncing Likes & Energy)
  magentaDim: 'rgba(244, 63, 94, 0.18)',
  magentaGlow: 'rgba(244, 63, 94, 0.35)',

  lime: '#10B981', // Cyber Lime (Online status, active audio meters)
  limeDim: 'rgba(16, 185, 129, 0.18)',
  limeGlow: 'rgba(16, 185, 129, 0.35)',

  amber: '#F59E0B', // Solar Amber (Stash / Highlights / Stars)
  amberDim: 'rgba(245, 158, 11, 0.18)',
  amberGlow: 'rgba(245, 158, 11, 0.35)',

  // Status Indicators
  success: '#10B981', // Cyber Lime
  error: '#F43F5E', // Electric Magenta
  errorDim: 'rgba(244, 63, 94, 0.15)',
  warning: '#F59E0B', // Solar Amber

  // Tactile Floating Overlays & Frosted Pill Tokens
  overlay: 'rgba(11, 15, 25, 0.88)',
  overlayRadial: 'rgba(234, 88, 12, 0.12)',
  glass: 'rgba(30, 38, 56, 0.78)', // Frosted glass pill navigation
  glassBorder: 'rgba(255, 255, 255, 0.08)',
  floatingPill: 'rgba(30, 38, 56, 0.85)',
} as const;

export type PaletteKey = keyof typeof PALETTE;
