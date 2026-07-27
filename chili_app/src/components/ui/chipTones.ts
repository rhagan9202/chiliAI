import { colors } from '../../theme/tokens'

export type ChipTone = 'default' | 'info' | 'success' | 'warning' | 'danger' | 'network'

/**
 * Text colour per chip tone. Extracted from `Chip.tsx` so the palette can be
 * contrast-asserted in tests — the `default` tone previously used `colors.b1`,
 * a *border* token, giving 1.33:1 and rendering tag chips near-invisible
 * (UXA-204).
 */
export const CHIP_TONE_COLORS: Record<ChipTone, string> = {
  default: colors.muted,
  info: colors.cyan,
  success: colors.green,
  warning: colors.amber,
  danger: colors.red,
  network: colors.purple,
}
