import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { RecordFeedConfig } from '../../../api/contracts'
import { RecordsSourcePanel } from '../RecordsSourcePanel'

const feeds: RecordFeedConfig[] = [
  {
    name: 'claims_feed',
    record_type: 'claim',
    source: 'file_upload',
    id_field: 'claim_id',
    record_schema: {
      claim_id: { type: 'string', display: 'Claim ID', required: true },
      provider_npi: { type: 'string', display: 'Provider NPI', required: true },
    },
    entities: [],
    relationships: [],
    observations: [],
  },
  {
    name: 'provider_feed',
    record_type: 'provider',
    source: 'api_push',
    id_field: 'provider_npi',
    record_schema: {},
    entities: [],
    relationships: [],
    observations: [],
  },
]

describe('RecordsSourcePanel', () => {
  it('selects feeds and parses pasted JSONL records', () => {
    const onFeedChange = vi.fn()
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onFeedChange={onFeedChange}
        onRowsParsed={onRowsParsed}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records feed'), {
      target: { value: 'provider_feed' },
    })
    fireEvent.change(screen.getByLabelText('Records format'), {
      target: { value: 'jsonl' },
    })
    fireEvent.change(screen.getByLabelText('Records content'), {
      target: {
        value: '{"claim_id":"c1","provider_npi":"1234567890"}\n{"claim_id":"c2","provider_npi":"2345678901"}',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Parse records' }))

    expect(onFeedChange).toHaveBeenCalledWith('provider_feed')
    expect(onRowsParsed).toHaveBeenCalledWith(
      [
        { claim_id: 'c1', provider_npi: '1234567890' },
        { claim_id: 'c2', provider_npi: '2345678901' },
      ],
      [],
    )
    expect(screen.getByText('claim')).toBeInTheDocument()
    expect(screen.getByText('claim_id')).toBeInTheDocument()
  })
})
