import { describe, expect, it } from 'vitest'

import type { DomainConfig, RuntimeEntity } from '../../api/contracts'
import { formatPropertyValue, getEntityProperties } from '../entityProperties'

function config(overrides: Partial<DomainConfig> = {}): DomainConfig {
  return {
    domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud', description: '' },
    entities: [
      {
        name: 'provider',
        display_label: 'Provider',
        natural_key: ['npi'],
        properties: {
          npi: { type: 'string', display: 'NPI' },
          organization_name: { type: 'string', display: 'Organization Name' },
          primary_taxonomy_code: { type: 'string', display: 'Primary Taxonomy' },
          practice_state: { type: 'string', display: 'Practice State' },
          enumeration_date: { type: 'date', display: 'Enumeration Date' },
          billed_amount: { type: 'decimal', display: 'Billed Amount' },
          claim_count: { type: 'integer', display: 'Claim Count' },
          is_active: { type: 'boolean', display: 'Currently Active' },
        },
      },
    ],
    relationships: [],
    capabilities: {
      timeseries: true,
      gnn: true,
      risk_scoring: true,
      rag_chat: true,
      explainability: true,
      peer_stats: true,
      structured_ingestion: true,
    },
    ingestion: {},
    alerts: { thresholds: {} },
    ui: { display_fields: { provider: { title: 'npi' } } },
    ...overrides,
  } as DomainConfig
}

function entity(properties: Record<string, unknown>): RuntimeEntity {
  return {
    id: 'provider-1',
    type: 'provider',
    properties,
  } as RuntimeEntity
}

describe('getEntityProperties', () => {
  it('labels every property from the domain configuration', () => {
    const views = getEntityProperties(
      entity({ practice_state: 'TN', organization_name: 'Redwood DME Group' }),
      config(),
    )

    expect(views.map((view) => view.label)).toEqual(['Organization Name', 'Practice State'])
  })

  it('orders properties by config declaration, not alphabetically', () => {
    // Alphabetically this is enumeration_date, organization_name, practice_state.
    const views = getEntityProperties(
      entity({
        practice_state: 'TN',
        enumeration_date: '2020-04-02',
        organization_name: 'Redwood DME Group',
      }),
      config(),
    )

    expect(views.map((view) => view.key)).toEqual([
      'organization_name',
      'practice_state',
      'enumeration_date',
    ])
  })

  it('humanizes a property the configuration does not describe', () => {
    const views = getEntityProperties(entity({ legacy_source_file: 'nppes.csv' }), config())

    expect(views[0]?.label).toBe('Legacy source file')
  })

  it('lists configured properties ahead of ones the configuration does not know', () => {
    const views = getEntityProperties(
      entity({ legacy_source_file: 'nppes.csv', practice_state: 'TN' }),
      config(),
    )

    expect(views.map((view) => view.key)).toEqual(['practice_state', 'legacy_source_file'])
  })

  it('omits the field already shown as the dossier title', () => {
    const views = getEntityProperties(entity({ npi: '1234567890', practice_state: 'TN' }), config())

    expect(views.map((view) => view.key)).toEqual(['practice_state'])
  })

  it('omits the field already shown as the dossier subtitle', () => {
    const withSubtitle = config({
      ui: { display_fields: { provider: { title: 'npi', subtitle: 'practice_state' } } },
    } as unknown as Partial<DomainConfig>)

    const views = getEntityProperties(
      entity({ npi: '1234567890', practice_state: 'TN', organization_name: 'Redwood' }),
      withSubtitle,
    )

    expect(views.map((view) => view.key)).toEqual(['organization_name'])
  })

  it('drops properties with no value rather than rendering a blank row', () => {
    const views = getEntityProperties(
      entity({ organization_name: '', practice_state: null, primary_taxonomy_code: '332B00000X' }),
      config(),
    )

    expect(views.map((view) => view.key)).toEqual(['primary_taxonomy_code'])
  })

  it('features the configured chip fields when the pack declares them', () => {
    const withChips = config({
      ui: { display_fields: { provider: { title: 'npi', chips: ['practice_state'] } } },
    } as unknown as Partial<DomainConfig>)

    const views = getEntityProperties(
      entity({ organization_name: 'Redwood', practice_state: 'TN' }),
      withChips,
    )

    expect(views.filter((view) => view.featured).map((view) => view.key)).toEqual(['practice_state'])
  })

  it('features the leading configured properties when the pack declares no chips', () => {
    const views = getEntityProperties(
      entity({
        organization_name: 'Redwood',
        primary_taxonomy_code: '332B00000X',
        practice_state: 'TN',
        enumeration_date: '2020-04-02',
        billed_amount: 1200.5,
      }),
      config(),
    )

    expect(views.filter((view) => view.featured).map((view) => view.key)).toEqual([
      'organization_name',
      'primary_taxonomy_code',
      'practice_state',
      'enumeration_date',
    ])
  })
})

describe('formatPropertyValue', () => {
  it('formats a date instead of echoing the ISO string', () => {
    expect(formatPropertyValue('2026-01-15', 'date')).toBe('Jan 15, 2026')
  })

  it('reads a date-only value as written, without shifting it by a time zone', () => {
    expect(formatPropertyValue('2020-04-02', 'date')).toBe('Apr 2, 2020')
  })

  it('leaves an unparseable date alone rather than showing Invalid Date', () => {
    expect(formatPropertyValue('sometime in 2020', 'date')).toBe('sometime in 2020')
  })

  it('groups integers', () => {
    expect(formatPropertyValue(1234567, 'integer')).toBe('1,234,567')
  })

  it('gives decimals a consistent two-place scale', () => {
    expect(formatPropertyValue(1200.5, 'decimal')).toBe('1,200.50')
  })

  it('renders booleans as words', () => {
    expect(formatPropertyValue(true, 'boolean')).toBe('Yes')
    expect(formatPropertyValue(false, 'boolean')).toBe('No')
  })

  it('joins list values', () => {
    expect(formatPropertyValue(['a', 'b'], 'list')).toBe('a, b')
  })

  it('passes strings through', () => {
    expect(formatPropertyValue('332B00000X', 'string')).toBe('332B00000X')
  })

  it('falls back to a readable string when the type is unknown', () => {
    expect(formatPropertyValue(42, undefined)).toBe('42')
  })
})
