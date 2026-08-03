import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type {
  EntityFeatureValueResponse,
  FeatureCatalogResponse,
} from '../../../api/contracts'
import { FeatureList } from '../FeatureList'
import { TypologyBadge } from '../TypologyBadge'

const catalog: FeatureCatalogResponse = {
  knowledge_base_id: 'kb-1',
  catalog_version: 'cms-fraud-features-v1',
  typologies: [
    {
      id: 'billing_spike',
      label: 'Billing spike',
      description: 'Unexpected billing acceleration.',
      entity_types: ['provider'],
      feature_ids: ['weekly_provider_billing_zscore'],
      policy_rule_ids: ['medicare.high_amount_claim'],
      playbook_ids: [],
      severity_hint: 'high',
    },
  ],
  features: [
    {
      id: 'weekly_provider_billing_zscore',
      label: 'Weekly provider billing z-score',
      description: 'Provider billing deviation from baseline.',
      entity_types: ['provider'],
      typology_ids: ['billing_spike'],
      value_type: 'decimal',
      transformation_version: 'peerstats-zscore-v1',
      source_mappings: [
        {
          source_ref: 'entity_derived_signals.weekly_provider_billing',
          source_type: 'derived_signal',
          raw_fields: ['metric', 'value'],
        },
      ],
      peer_dimensions: ['specialty'],
      threshold_hints: { high: 0.8 },
    },
  ],
}

const values: EntityFeatureValueResponse[] = [
  {
    entity_type: 'provider',
    entity_id: 'npi-123',
    feature_id: 'weekly_provider_billing_zscore',
    value: 4.2,
    normalized_value: 0.84,
    catalog_version: 'cms-fraud-features-v1',
    transformation_version: 'peerstats-zscore-v1',
    source_refs: ['entity_derived_signals.weekly_provider_billing', 'raw_records.claims_feed'],
    observed_at: '2026-08-02T12:00:00Z',
    score_run_id: 'score-run-1',
  },
]

describe('TypologyBadge', () => {
  it('renders the typology label and severity hint', () => {
    render(<TypologyBadge typology={catalog.typologies[0]} />)

    expect(screen.getByText('Billing spike')).toBeInTheDocument()
    expect(screen.getByText('Billing spike')).toHaveAttribute(
      'title',
      'High severity: Unexpected billing acceleration.',
    )
  })
})

describe('FeatureList', () => {
  it('renders feature labels, typologies, source refs, and normalized values', () => {
    render(<FeatureList catalog={catalog} values={values} />)

    expect(screen.getByText('Weekly provider billing z-score')).toBeInTheDocument()
    expect(screen.getByText('Provider billing deviation from baseline.')).toBeInTheDocument()
    expect(screen.getByText('Billing spike')).toBeInTheDocument()
    expect(screen.getByText('84%')).toBeInTheDocument()
    expect(screen.getByText('Raw value 4.2')).toBeInTheDocument()
    expect(screen.getByText('entity_derived_signals.weekly_provider_billing')).toBeInTheDocument()
    expect(screen.getByText('raw_records.claims_feed')).toBeInTheDocument()
  })

  it('falls back to feature ids when the catalog is unavailable', () => {
    render(<FeatureList catalog={null} values={values} />)

    expect(screen.getByText('weekly provider billing zscore')).toBeInTheDocument()
    expect(screen.queryByText('Billing spike')).not.toBeInTheDocument()
  })

  it('renders a useful empty state', () => {
    render(<FeatureList catalog={catalog} values={[]} />)

    expect(screen.getByText('No feature values')).toBeInTheDocument()
    expect(screen.getByText('This entity does not have scored feature values yet.')).toBeInTheDocument()
  })
})
