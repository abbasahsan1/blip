export const PALETTE = {
  // Deep Obsidian Canvas & Surfaces (Tactile Audio-First Experience)
  bg: '#07080B', // Deep Obsidian canvas
  surface: '#11131B', // Surface Slate
  surfaceSubtle: '#0D0F16',
  card: '#161924', // Elevated dark module chassis
  cardHover: '#1E2232',
  cardGlass: 'rgba(17, 19, 27, 0.85)',

  // Mechanical / Neon Borders
  border: '#242938', // Dark slate groove border
  borderSubtle: '#181C28',
  borderNeon: '#7C3AED',
  borderGlass: 'rgba(124, 58, 237, 0.25)',

  // High-Contrast Readout Typography
  text: '#FFFFFF', // Pure White signal
  textSecondary: '#94A3B8', // Muted Silver readout
  textMuted: '#64748B', // Muted Slate acoustic low
  primary: '#FFFFFF',

  // Expressive Social & Frequency Accents
  accent: '#7C3AED', // Accent Neon Violet
  accentDim: 'rgba(124, 58, 237, 0.18)',
  accentGlow: 'rgba(124, 58, 237, 0.35)',

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
  overlay: 'rgba(7, 8, 11, 0.88)',
  overlayRadial: 'rgba(124, 58, 237, 0.12)',
  glass: 'rgba(17, 19, 27, 0.78)', // Frosted glass pill navigation
  glassBorder: 'rgba(255, 255, 255, 0.08)',
  floatingPill: 'rgba(17, 19, 27, 0.85)',
} as const;

export type PaletteKey = keyof typeof PALETTE;
