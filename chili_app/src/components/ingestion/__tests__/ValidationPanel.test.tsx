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

  it('renders a Prerequisites section with info tone when only prerequisite issues are present', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'missing-kb',
        source: 'client',
        severity: 'error',
        kind: 'prerequisite',
        message: 'Select a knowledge base before submitting.',
      },
      {
        id: 'missing-source',
        source: 'client',
        severity: 'error',
        kind: 'prerequisite',
        message: 'Choose Documents or Structured Records before submitting.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    const prereq = screen.getByRole('region', { name: /prerequisites/i })
    expect(within(prereq).getByText('2 to do')).toBeInTheDocument()
    expect(within(prereq).getByText('Select a knowledge base before submitting.')).toBeInTheDocument()
    expect(within(prereq).getByText('Choose Documents or Structured Records before submitting.')).toBeInTheDocument()

    // The "Ready for submission" empty state must NOT appear when prerequisites are present.
    expect(screen.queryByText('Ready for submission')).not.toBeInTheDocument()

    // No source-grouped Client check / Backend response section appears when no content issues exist.
    expect(screen.queryByRole('region', { name: /client check/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /backend response/i })).not.toBeInTheDocument()
  })

  it('renders both Prerequisites and Client check sections when both kinds are present', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'missing-kb',
        source: 'client',
        severity: 'error',
        kind: 'prerequisite',
        message: 'Select a knowledge base before submitting.',
      },
      {
        id: 'row-1-npi-pattern',
        source: 'client',
        severity: 'error',
        message: 'Row 1 field Provider NPI does not match ^[0-9]{10}$.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    const prereq = screen.getByRole('region', { name: /prerequisites/i })
    expect(within(prereq).getByText('1 to do')).toBeInTheDocument()

    const clientGroup = screen.getByRole('region', { name: /client check/i })
    expect(within(clientGroup).getByText('1 issue')).toBeInTheDocument()
    expect(
      within(clientGroup).getByText('Row 1 field Provider NPI does not match ^[0-9]{10}$.'),
    ).toBeInTheDocument()
  })

  it('renders only the existing source-grouped sections when there are no prerequisite issues', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'row-1-npi-pattern',
        source: 'client',
        severity: 'error',
        message: 'Row 1 field Provider NPI does not match ^[0-9]{10}$.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    expect(screen.queryByRole('region', { name: /prerequisites/i })).not.toBeInTheDocument()
    const clientGroup = screen.getByRole('region', { name: /client check/i })
    expect(within(clientGroup).getByText('1 issue')).toBeInTheDocument()
  })
})
