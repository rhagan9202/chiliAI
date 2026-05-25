import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { IngestionStepId } from '../../../lib/ingestion/types'
import { IngestionStepper } from '../IngestionStepper'

describe('IngestionStepper', () => {
  it('renders ordered wizard steps with the current step marked', () => {
    render(
      <IngestionStepper
        currentStep="preview"
        completedStepIds={new Set<IngestionStepId>(['knowledge-base', 'source'])}
        errorStepIds={new Set<IngestionStepId>()}
      />,
    )

    const list = screen.getByRole('list', { name: 'Ingestion progress' })
    const steps = within(list).getAllByRole('listitem')

    expect(steps).toHaveLength(6)
    expect(steps.map((step) => within(step).getByText(/Knowledge base|Source|Preview|Validate|Submit|Runs/).textContent)).toEqual([
      'Knowledge base',
      'Source',
      'Preview',
      'Validate',
      'Submit',
      'Runs',
    ])
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Preview')
  })

  it('shows completed and error status labels with error taking precedence', () => {
    render(
      <IngestionStepper
        currentStep="validate"
        completedStepIds={new Set<IngestionStepId>(['knowledge-base', 'source'])}
        errorStepIds={new Set<IngestionStepId>(['source', 'submit'])}
      />,
    )

    expect(screen.getByText('Knowledge base').closest('li')).toHaveTextContent('Complete')
    expect(screen.getByText('Source').closest('li')).toHaveTextContent('Needs attention')
    expect(screen.getByText('Submit').closest('li')).toHaveTextContent('Needs attention')
    expect(screen.queryAllByText('Complete')).toHaveLength(1)
  })
})
