import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ValidationIssue } from '../../../lib/ingestion/types'
import { RecordsPreviewTable } from '../RecordsPreviewTable'

describe('RecordsPreviewTable', () => {
  it('renders an empty state when no records are parsed', () => {
    render(<RecordsPreviewTable rows={[]} issues={[]} />)

    expect(screen.getByText('No records parsed')).toBeInTheDocument()
  })

  it('renders row numbers, values, and per-row status chips', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'row-2-missing',
        message: 'Provider is required.',
        rowIndex: 1,
        severity: 'error',
        source: 'client',
      },
      {
        id: 'row-2-format',
        message: 'Amount must be numeric.',
        rowIndex: 1,
        severity: 'warning',
        source: 'client',
      },
    ]

    render(
      <RecordsPreviewTable
        issues={issues}
        rows={[
          { claim_id: 'c1', provider_npi: '1234567890', billed_amount: 99.5 },
          { claim_id: 'c2', provider_npi: '', billed_amount: 'invalid' },
        ]}
      />,
    )

    const table = screen.getByRole('table', { name: /records preview/i })
    expect(within(table).getByRole('columnheader', { name: 'claim_id' })).toBeInTheDocument()
    expect(within(table).getByText('c1')).toBeInTheDocument()
    expect(within(table).getByText('99.5')).toBeInTheDocument()
    expect(within(table).getByText('valid')).toBeInTheDocument()
    expect(within(table).getByText('2 issues')).toBeInTheDocument()
  })
})
