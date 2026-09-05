import React from 'react';
import Svg, { Path, Rect, Circle, Line } from 'react-native-svg';

interface IconProps {
  size?: number;
  color?: string;
}

/**
 * Tactile Play Vector Mark
 */
export function PlayMark({ size = 20, color = '#ffffff' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M7 5.5V18.5L18.5 12L7 5.5Z"
        fill={color}
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

/**
 * Tactile Pause Vector Mark
 */
export function PauseMark({ size = 20, color = '#ffffff' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Rect x="6" y="5" width="4" height="14" rx="1" fill={color} />
      <Rect x="14" y="5" width="4" height="14" rx="1" fill={color} />
    </Svg>
  );
}

/**
 * Audio Reaction / Like Mark (Filled or Outlined)
 */
export function HeartMark({ size = 20, color = '#ffffff', filled = false }: IconProps & { filled?: boolean }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 20.25S3.75 15.3 3.75 9.75A5.25 5.25 0 0 1 12 5.5a5.25 5.25 0 0 1 8.25 4.25c0 5.55-8.25 10.5-8.25 10.5Z"
        fill={filled ? color : 'none'}
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

/**
 * Feed Console Navigation Mark (Acoustic Spectrum Bars)
 */
export function FeedConsoleMark({ size = 20, color = '#71717a' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Line x1="5" y1="8" x2="5" y2="16" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <Line x1="9.5" y1="4" x2="9.5" y2="20" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <Line x1="14" y1="7" x2="14" y2="17" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
      <Line x1="18.5" y1="10" x2="18.5" y2="14" stroke={color} strokeWidth="2.2" strokeLinecap="round" />
    </Svg>
  );
}

/**
 * Upload Console Navigation Mark (Audio Input / Direct Track Inject)
 */
export function UploadConsoleMark({ size = 20, color = '#71717a' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx="12" cy="12" r="8.5" stroke={color} strokeWidth="1.8" />
      <Line x1="12" y1="8" x2="12" y2="16" stroke={color} strokeWidth="2" strokeLinecap="round" />
      <Line x1="8" y1="12" x2="16" y2="12" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </Svg>
  );
}

/**
 * Profile Console Navigation Mark (Operator Console)
 */
export function ProfileConsoleMark({ size = 20, color = '#71717a' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Circle cx="12" cy="8" r="4" stroke={color} strokeWidth="1.8" />
      <Path
        d="M5 19.5C5 16.5 8 14.5 12 14.5C16 14.5 19 16.5 19 19.5"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </Svg>
  );
}

/**
 * Acoustic Deck Disc Mark (Replaces emoji for empty feed state)
 */
export function AcousticDeckMark({ size = 48, color = '#3f3f46' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 48 48" fill="none">
      <Circle cx="24" cy="24" r="21" stroke={color} strokeWidth="2" />
      <Circle cx="24" cy="24" r="14" stroke={color} strokeWidth="1.5" strokeDasharray="3 3" />
      <Circle cx="24" cy="24" r="6" stroke={color} strokeWidth="2" />
      <Circle cx="24" cy="24" r="2" fill={color} />
    </Svg>
  );
}

/**
 * Audio Reel Mark (Replaces emoji for upload dropzone)
 */
export function AudioReelMark({ size = 32, color = '#71717a' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <Rect x="3" y="6" width="26" height="20" rx="3" stroke={color} strokeWidth="1.8" />
      <Circle cx="10" cy="16" r="3.5" stroke={color} strokeWidth="1.5" />
      <Circle cx="22" cy="16" r="3.5" stroke={color} strokeWidth="1.5" />
      <Line x1="10" y1="16" x2="22" y2="16" stroke={color} strokeWidth="1.5" />
      <Path d="M7 22H25" stroke={color} strokeWidth="1.2" />
    </Svg>
  );
}

/**
 * Status Alert Mark (Replaces emoji warning)
 */
export function StatusAlertMark({ size = 16, color = '#ef4444' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <Circle cx="8" cy="8" r="7" stroke={color} strokeWidth="1.5" />
      <Line x1="8" y1="4.5" x2="8" y2="8.5" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <Circle cx="8" cy="11.5" r="0.85" fill={color} />
    </Svg>
  );
}

/**
 * Status Check Mark (Replaces emoji check)
 */
export function StatusCheckMark({ size = 16, color = '#10b981' }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 16 16" fill="none">
      <Circle cx="8" cy="8" r="7" stroke={color} strokeWidth="1.5" />
      <Path d="M4.5 8.2L6.8 10.5L11.5 5.8" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}
