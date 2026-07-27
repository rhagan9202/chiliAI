/**
 * WCAG relative-luminance contrast, used to keep the palette honest.
 *
 * Small text needs *more* contrast, not less, and this product renders 10-11px
 * labels in the quietest token it has — so the ratios are asserted in tests
 * rather than eyeballed (UXA-204).
 */

function expandHex(hex: string): string {
  const value = hex.replace('#', '')
  return value.length === 3
    ? value
        .split('')
        .map((char) => char + char)
        .join('')
    : value
}

function channelLuminance(channel: number): number {
  const c = channel / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

/** Relative luminance per WCAG 2.x. */
export function relativeLuminance(hex: string): number {
  const value = expandHex(hex)
  const r = Number.parseInt(value.slice(0, 2), 16)
  const g = Number.parseInt(value.slice(2, 4), 16)
  const b = Number.parseInt(value.slice(4, 6), 16)
  return (
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)
  )
}

/** Contrast ratio between two colours, from 1 (identical) to 21 (black/white). */
export function contrastRatio(foreground: string, background: string): number {
  const a = relativeLuminance(foreground)
  const b = relativeLuminance(background)
  const lighter = Math.max(a, b)
  const darker = Math.min(a, b)
  return (lighter + 0.05) / (darker + 0.05)
}
