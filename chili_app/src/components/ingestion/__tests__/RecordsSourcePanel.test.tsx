import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  it('selects feeds, clears feed selection, and parses pasted JSONL records', () => {
    const onFeedChange = vi.fn()
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onFileChange={vi.fn()}
        onFeedChange={onFeedChange}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records feed'), {
      target: { value: 'provider_feed' },
    })
    fireEvent.change(screen.getByLabelText('Records feed'), {
      target: { value: '' },
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
    expect(onFeedChange).toHaveBeenCalledWith(null)
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

  it('parses pasted CSV records from the parse button', () => {
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records format'), {
      target: { value: 'csv' },
    })
    fireEvent.change(screen.getByLabelText('Records content'), {
      target: {
        value: 'claim_id,provider_npi,billed_amount\nc1,1234567890,99.50\nc2,2345678901,120.25\n',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Parse records' }))

    expect(onRowsParsed).toHaveBeenCalledWith(
      [
        { claim_id: 'c1', provider_npi: '1234567890', billed_amount: '99.50' },
        { claim_id: 'c2', provider_npi: '2345678901', billed_amount: '120.25' },
      ],
      [],
    )
  })

  it('selects and parses a CSV records file for file upload feeds', async () => {
    const onFileChange = vi.fn()
    const onRowsParsed = vi.fn()
    const file = new File(['claim_id,provider_npi\nc1,1234567890\n'], 'claims.csv', {
      type: 'text/csv',
    })

    const { rerender } = render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [file] },
    })
    rerender(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={file}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Parse records' }))

    expect(onFileChange).toHaveBeenCalledWith(file)
    expect(await screen.findByText('claims.csv')).toBeInTheDocument()
    await waitFor(() => {
      expect(onRowsParsed).toHaveBeenCalledWith(
        [{ claim_id: 'c1', provider_npi: '1234567890' }],
        [],
      )
    })
  })
})
