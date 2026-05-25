import { CheckCircle2, Circle, CircleAlert } from 'lucide-react'

import { Chip } from '../ui/Chip'
import type { IngestionStepId } from '../../lib/ingestion/types'
import './ingestion.css'

type IngestionStepperProps = {
  currentStep: IngestionStepId
  completedStepIds: Set<IngestionStepId>
  errorStepIds: Set<IngestionStepId>
}

const steps: Array<{ id: IngestionStepId; label: string }> = [
  { id: 'knowledge-base', label: 'Knowledge base' },
  { id: 'source', label: 'Source' },
  { id: 'preview', label: 'Preview' },
  { id: 'validate', label: 'Validate' },
  { id: 'submit', label: 'Submit' },
  { id: 'runs', label: 'Runs' },
]

export function IngestionStepper({
  currentStep,
  completedStepIds,
  errorStepIds,
}: IngestionStepperProps) {
  return (
    <nav className="ingestion-stepper" aria-label="Ingestion wizard">
      <ol className="ingestion-stepper__list" aria-label="Ingestion progress">
        {steps.map((step, index) => {
          const isCurrent = step.id === currentStep
          const hasError = errorStepIds.has(step.id)
          const isComplete = completedStepIds.has(step.id)
          const Icon = hasError ? CircleAlert : isComplete ? CheckCircle2 : Circle

          return (
            <li
              key={step.id}
              className={[
                'ingestion-stepper__item',
                isCurrent ? 'ingestion-stepper__item--active' : '',
                hasError ? 'ingestion-stepper__item--error' : '',
                isComplete && !hasError ? 'ingestion-stepper__item--complete' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              aria-current={isCurrent ? 'step' : undefined}
            >
              <div className="ingestion-stepper__marker" aria-hidden="true">
                <Icon size={16} strokeWidth={2.2} />
              </div>
              <div className="ingestion-stepper__body">
                <span className="ingestion-stepper__index">Step {index + 1}</span>
                <span className="ingestion-stepper__label">{step.label}</span>
              </div>
              {hasError ? (
                <Chip tone="danger" label="Needs attention" />
              ) : isComplete ? (
                <Chip tone="success" label="Complete" />
              ) : null}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
