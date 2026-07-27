import { describe, expect, it } from 'vitest'

import { contrastRatio } from '../contrast'
import { CHIP_TONE_COLORS } from '../../components/ui/chipTones'
import { colors } from '../tokens'

/** Surfaces any text token can legitimately sit on. */
const SURFACES = ['bg', 's1', 's2', 's3'] as const

/**
 * Tokens used for text. `muted` is included deliberately: it carries the label
 * of every *inactive* tab and filter chip in the product, plus KPI sublabels and
 * risk-badge labels, so it is body text by any reasonable reading — not
 * decoration (UXA-204).
 */
const TEXT_TOKENS = ['text', 'dim', 'muted', 'cyan', 'amber', 'red', 'green'] as const

const AA_NORMAL_TEXT = 4.5

describe('contrastRatio', () => {
  it('reports the maximum ratio for black on white', () => {
    expect(contrastRatio('#ffffff', '#000000')).toBeCloseTo(21, 1)
  })

  it('reports 1 for a colour against itself', () => {
    expect(contrastRatio('#3d5070', '#3d5070')).toBeCloseTo(1, 5)
  })

  it('is order-independent', () => {
    expect(contrastRatio('#8899bb', '#05080f')).toBeCloseTo(
      contrastRatio('#05080f', '#8899bb'),
      5,
    )
  })

  it('accepts shorthand hex', () => {
    expect(contrastRatio('#fff', '#000')).toBeCloseTo(21, 1)
  })
})

describe('theme token contrast', () => {
  for (const token of TEXT_TOKENS) {
    for (const surface of SURFACES) {
      it(`${token} on ${surface} meets WCAG AA for normal text`, () => {
        const ratio = contrastRatio(colors[token], colors[surface])
        expect(
          ratio,
          `--c-${token} (${colors[token]}) on --c-${surface} (${colors[surface]}) is ${ratio.toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT)
      })
    }
  }

  it('gives interactive control boundaries the 3:1 WCAG 1.4.11 floor', () => {
    for (const surface of SURFACES) {
      const ratio = contrastRatio(colors.controlBorder, colors[surface])
      expect(
        ratio,
        `--c-control-border on --c-${surface} is ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(3)
    }
  })

  it('renders every chip tone as readable text, not a border colour', () => {
    // The `default` tone shipped as `colors.b1` — a *border* token used as text,
    // measuring 1.33:1. That is what made the BILLING / PEER DEVIATION tag chips
    // and the evidence score chips effectively invisible (UXA-204).
    for (const [tone, value] of Object.entries(CHIP_TONE_COLORS)) {
      for (const surface of ['s2', 's3'] as const) {
        const ratio = contrastRatio(value, colors[surface])
        expect(
          ratio,
          `chip tone '${tone}' (${value}) on --c-${surface} is ${ratio.toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT)
      }
    }
  })

  it('keeps muted quieter than dim so the type hierarchy survives the fix', () => {
    expect(contrastRatio(colors.muted, colors.bg)).toBeLessThan(
      contrastRatio(colors.dim, colors.bg),
    )
  })
})
