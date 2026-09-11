export const PALETTE = {
  // Deep Obsidian Canvas & Surfaces (Tactile Audio-First Experience)
  bg: '#090A0F', // Deep Obsidian canvas
  surface: '#131825', // Surface Slate
  surfaceSubtle: '#131825',
  card: '#131825', // Elevated dark module chassis
  cardHover: '#1E293B',
  cardGlass: 'rgba(19, 24, 37, 0.85)',

  // Mechanical / Neon Borders
  border: '#1E293B', // Dark slate groove border
  borderSubtle: '#131825',
  borderNeon: '#FF6B00',
  borderGlass: 'rgba(255, 107, 0, 0.25)',

  // High-Contrast Readout Typography
  text: '#FFFFFF', // Pure White signal
  textSecondary: '#94A3B8', // Muted Silver readout
  textMuted: '#94A3B8', // Muted Slate acoustic low
  primary: '#FF6B00',

  // Expressive Social & Frequency Accents
  accent: '#FF6B00', // Accent Orange
  accentDim: 'rgba(255, 107, 0, 0.18)',
  accentGlow: 'rgba(255, 107, 0, 0.35)',

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
