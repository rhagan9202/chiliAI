import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import type { ValidationIssue, ValidationSource } from '../../lib/ingestion/types'
import './ingestion.css'

type ValidationPanelProps = {
  issues: ValidationIssue[]
}

const sourceLabels: Record<ValidationSource, string> = {
  client: 'Client check',
  backend: 'Backend response',
}

const sourceOrder: ValidationSource[] = ['client', 'backend']

function countLabel(count: number): string {
  return `${count} ${count === 1 ? 'issue' : 'issues'}`
}

export function ValidationPanel({ issues }: ValidationPanelProps) {
  if (issues.length === 0) {
    return (
      <EmptyState
        title="Ready for submission"
        description="No validation issues were found."
      />
    )
  }

  return (
    <div className="ingestion-validation-panel">
      {sourceOrder.map((source) => {
        const sourceIssues = issues.filter((issue) => issue.source === source)

        if (sourceIssues.length === 0) {
          return null
        }

        const label = sourceLabels[source]

        return (
          <section
            key={source}
            className="ingestion-validation-panel__group"
            aria-labelledby={`validation-${source}-title`}
          >
            <div className="ingestion-validation-panel__group-header">
              <h3
                id={`validation-${source}-title`}
                className="ingestion-validation-panel__group-title"
              >
                {label}
              </h3>
              <Chip
                tone={sourceIssues.some((issue) => issue.severity === 'error') ? 'danger' : 'warning'}
                label={countLabel(sourceIssues.length)}
              />
            </div>
            <ul className="ingestion-validation-panel__list">
              {sourceIssues.map((issue) => (
                <li key={issue.id} className="ingestion-validation-panel__issue">
                  <span
                    className={[
                      'ingestion-validation-panel__severity',
                      `ingestion-validation-panel__severity--${issue.severity}`,
                    ].join(' ')}
                  >
                    {issue.severity}
                  </span>
                  <span className="ingestion-validation-panel__message">{issue.message}</span>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
