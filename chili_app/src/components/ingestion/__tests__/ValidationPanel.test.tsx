import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ValidationIssue } from '../../../lib/ingestion/types'
import { ValidationPanel } from '../ValidationPanel'

describe('ValidationPanel', () => {
  it('renders an empty state when there are no validation issues', () => {
    render(<ValidationPanel issues={[]} />)

    expect(screen.getByText('Ready for submission')).toBeInTheDocument()
  })

  it('groups validation issues by source label and shows counts and messages', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'missing-kb',
        source: 'client',
        severity: 'error',
        message: 'Select a knowledge base before submitting.',
      },
      {
        id: 'backend-reject',
        source: 'backend',
        severity: 'error',
        message: 'The selected feed is disabled.',
      },
      {
        id: 'large-file',
        source: 'client',
        severity: 'warning',
        message: 'claims.csv is larger than 50 MB.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    const clientGroup = screen.getByRole('region', { name: /client check/i })
    const backendGroup = screen.getByRole('region', { name: /backend response/i })

    expect(within(clientGroup).getByText('2 issues')).toBeInTheDocument()
    expect(within(clientGroup).getByText('Select a knowledge base before submitting.')).toBeInTheDocument()
    expect(within(clientGroup).getByText('claims.csv is larger than 50 MB.')).toBeInTheDocument()
    expect(within(backendGroup).getByText('1 issue')).toBeInTheDocument()
    expect(within(backendGroup).getByText('The selected feed is disabled.')).toBeInTheDocument()
  })
})
