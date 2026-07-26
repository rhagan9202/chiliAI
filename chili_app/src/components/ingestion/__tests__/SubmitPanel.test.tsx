import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SubmitPanel } from '../SubmitPanel'

describe('SubmitPanel', () => {
  it('runs ingestion through one primary action', () => {
    const onRunIngestion = vi.fn()

    render(
      <SubmitPanel
        sourceType="documents"
        canRunIngestion
        runPending={false}
        onRunIngestion={onRunIngestion}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Run ingestion' }))
    expect(onRunIngestion).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Documents ready')).toBeInTheDocument()
  })

  it('shows records readiness and disables run when not ready', () => {
    render(
      <SubmitPanel
        sourceType="records"
        canRunIngestion={false}
        runPending={false}
        onRunIngestion={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeDisabled()
    expect(screen.getByText('Parse records')).toBeInTheDocument()
  })

  it('shows pending copy without changing the run action label', () => {
    render(
      <SubmitPanel
        sourceType="documents"
        canRunIngestion
        runPending
        onRunIngestion={vi.fn()}
      />,
    )

    const panel = screen.getByRole('region', { name: /run ingestion/i })
    expect(within(panel).getByRole('button', { name: 'Run ingestion' })).toBeDisabled()
    expect(within(panel).getByText('Running ingestion')).toBeInTheDocument()
  })
})
