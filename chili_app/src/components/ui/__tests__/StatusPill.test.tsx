import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusPill } from '../StatusPill'
import { priorityToneForValue, statusToneForValue } from '../statusPill'

describe('StatusPill', () => {
  it('renders a semantic status label with accessible context', () => {
    render(<StatusPill context="Workflow state" label="Running" tone="warning" />)

    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByLabelText('Workflow state: Running')).toBeInTheDocument()
    expect(screen.getByTestId('status-pill-icon')).toHaveAttribute('aria-hidden', 'true')
  })

  it('uses the visible label as the accessible name when context is absent', () => {
    render(<StatusPill label="Open" tone="info" />)

    expect(screen.getByLabelText('Open')).toBeInTheDocument()
  })

  it('supports compact rendering for dense metadata rows', () => {
    render(<StatusPill compact label="SLA current" tone="success" />)

    expect(screen.getByLabelText('SLA current')).toHaveClass('status-pill--compact')
  })
})

describe('status pill tone helpers', () => {
  it('maps workflow and case states to operational tones', () => {
    expect(statusToneForValue('failed')).toBe('danger')
    expect(statusToneForValue('completed')).toBe('success')
    expect(statusToneForValue('open')).toBe('info')
    expect(statusToneForValue('closed')).toBe('success')
  })

  it('maps priority labels to operational tones', () => {
    expect(priorityToneForValue('critical')).toBe('danger')
    expect(priorityToneForValue('high')).toBe('warning')
    expect(priorityToneForValue('low')).toBe('info')
  })
})
