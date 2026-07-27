import { describe, expect, it } from 'vitest'

import type { DomainConfig } from '../../api/contracts'
import { starterPrompts } from '../starterPrompts'

function config(overrides: Partial<DomainConfig> = {}): DomainConfig {
  return {
    domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud', description: '' },
    entities: [
      { name: 'provider', display_label: 'Provider', properties: {} },
      { name: 'claim', display_label: 'Claim', properties: {} },
    ],
    relationships: [
      { name: 'submitted_by', display_label: 'Submitted By', source: 'claim', target: 'provider' },
    ],
    capabilities: {},
    ingestion: {},
    alerts: { thresholds: {} },
    ...overrides,
  } as unknown as DomainConfig
}

describe('starterPrompts', () => {
  it('names the pack’s own entity types rather than hardcoded domain words', () => {
    // An empty chat box against an unfamiliar corpus is the hardest possible
    // starting point (UXA-403), and the openers must follow the domain pack.
    const prompts = starterPrompts(config())

    expect(prompts.some((prompt) => prompt.includes('Provider'))).toBe(true)
  })

  it('changes with the domain pack', () => {
    const housing = config({
      entities: [{ name: 'installation', display_label: 'Installation', properties: {} }],
      relationships: [],
    } as unknown as Partial<DomainConfig>)

    const prompts = starterPrompts(housing)

    expect(prompts.some((prompt) => prompt.includes('Installation'))).toBe(true)
    expect(prompts.some((prompt) => prompt.includes('Provider'))).toBe(false)
  })

  it('uses a configured relationship to suggest a connection question', () => {
    const prompts = starterPrompts(config())

    expect(prompts.some((prompt) => prompt.includes('Submitted By'))).toBe(true)
  })

  it('offers a bounded set so the empty state stays readable', () => {
    const many = config({
      entities: Array.from({ length: 12 }, (_, index) => ({
        name: `type-${index}`,
        display_label: `Type ${index}`,
        properties: {},
      })),
    } as unknown as Partial<DomainConfig>)

    expect(starterPrompts(many).length).toBeLessThanOrEqual(4)
  })

  it('returns nothing when there is no configuration to derive from', () => {
    expect(starterPrompts(null)).toEqual([])
  })

  it('still offers something for a pack with no relationships', () => {
    const bare = config({ relationships: [] } as unknown as Partial<DomainConfig>)

    expect(starterPrompts(bare).length).toBeGreaterThan(0)
  })
})
