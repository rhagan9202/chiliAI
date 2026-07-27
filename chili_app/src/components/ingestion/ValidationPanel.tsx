import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import type { ValidationIssue, ValidationSource } from '../../lib/ingestion/types'
import { countLabel } from '../../utils/countLabel'
import './ingestion.css'

type ValidationPanelProps = {
  issues: ValidationIssue[]
}

const sourceLabels: Record<ValidationSource, string> = {
  client: 'Checked before upload',
  backend: 'Checked after upload',
}

const sourceOrder: ValidationSource[] = ['client', 'backend']

function issueCountLabel(count: number): string {
  return countLabel(count, 'issue')
}

function prerequisiteCountLabel(count: number): string {
  return `${count} to do`
}

export function ValidationPanel({ issues }: ValidationPanelProps) {
  const prerequisiteIssues = issues.filter((issue) => issue.kind === 'prerequisite')
  const contentIssues = issues.filter((issue) => (issue.kind ?? 'content') === 'content')

  if (prerequisiteIssues.length === 0 && contentIssues.length === 0) {
    return (
      <EmptyState
        title="Ready for submission"
        description="No validation issues were found."
      />
    )
  }

  return (
    <div className="ingestion-validation-panel">
      {prerequisiteIssues.length > 0 ? (
        <section
          className="ingestion-validation-panel__group"
          aria-labelledby="validation-prerequisites-title"
        >
          <div className="ingestion-validation-panel__group-header">
            <h3
              id="validation-prerequisites-title"
              className="ingestion-validation-panel__group-title"
            >
              Prerequisites
            </h3>
            <Chip tone="info" label={prerequisiteCountLabel(prerequisiteIssues.length)} />
          </div>
          <ul className="ingestion-validation-panel__list">
            {prerequisiteIssues.map((issue) => (
              <li key={issue.id} className="ingestion-validation-panel__issue">
                <span className="ingestion-validation-panel__severity ingestion-validation-panel__severity--prerequisite">
                  to do
                </span>
                <span className="ingestion-validation-panel__message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {sourceOrder.map((source) => {
        const sourceIssues = contentIssues.filter((issue) => issue.source === source)

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
                label={issueCountLabel(sourceIssues.length)}
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
