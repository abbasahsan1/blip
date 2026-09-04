# Blipp Platform - Design System Specifications (Impeccable)

## Design Principles
1. **High Information Density with Generous Breathing Room**: Clean tabular and card layouts with intentional whitespace, never cramped or messy.
2. **Monochrome Dominance with Intentional Accents**: Deep graphite/zinc backgrounds (`#09090b`), crisp border boundaries (`#27272a`), solid tactile primary controls (`#ffffff` on `#09090b` or `#2563eb`), and subtle semantic indicators.
3. **Typography First**: Clean system sans typography stack with negative tracking on headings (`-0.02em`), generous line-height on body (`1.5`), and strict contrast ratios (WCAG AAA compliant).
4. **Zero AI Clichés**:
   - ❌ No purple-to-cyan gradient borders or backgrounds.
   - ❌ No nested cards inside cards inside cards.
   - ❌ No low-contrast dark-gray-on-darker-gray labels.
   - ❌ No generic "Welcome to..." banner fluff.
   - ✅ Clean, purposeful, engineering-grade UI controls.

## Design Tokens

### Color Palette
- **Canvas / Background**: `#09090b` (Deep Zinc)
- **Elevated Surface**: `#121215` (Panel Surface)
- **Card Surface**: `#18181b` (Interactive Surface)
- **Subtle Border**: `#27272a` (Crisp 1px Divider)
- **Border Focus / Active**: `#3b82f6` (Clear Focus Ring)
- **Text Primary**: `#f4f4f5` (High Contrast Crisp White)
- **Text Secondary**: `#a1a1aa` (Readable Zinc, 4.5:1+ contrast)
- **Text Muted**: `#71717a`
- **Primary Action (Brand)**: `#ffffff` (Solid tactile contrast on dark)
- **Primary Action Text**: `#09090b`
- **Primary Action Hover**: `#e4e4e7`
- **Accent Blue**: `#2563eb` / `#3b82f6`
- **Success**: `#10b981` / background `#064e3b26`
- **Error / Danger**: `#ef4444` / background `#7f1d1d26`

### Typography & Spacing
- **Base Grid**: 4px / 8px scale (`4`, `8`, `12`, `16`, `20`, `24`, `32`, `48`)
- **Border Radius**: Small (`4px`), Medium (`8px`), Large (`12px`)
- **Interactive Inputs**: Height 42px, padding horizontal 14px, border 1px solid `#27272a`, background `#09090b`.
