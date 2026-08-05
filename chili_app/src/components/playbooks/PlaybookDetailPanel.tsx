import type { PlaybookResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'

type PlaybookDetailPanelProps = {
  isError?: boolean
  isLoading?: boolean
  playbook: PlaybookResponse | null
}

function listLabel(items: string[] | undefined, fallback: string) {
  return items && items.length > 0 ? items.join(', ') : fallback
}

export function PlaybookDetailPanel({
  isError = false,
  isLoading = false,
  playbook,
}: PlaybookDetailPanelProps) {
  return (
    <Card compact>
      <div aria-label="Playbook detail" className="metric-stack" role="group">
        <div className="metric-row">
          <strong>{playbook?.title ?? 'Playbook detail'}</strong>
          {playbook ? <Chip label={playbook.version} tone="network" /> : null}
        </div>

        {isLoading ? <LoadingState label="Loading playbook" /> : null}
        {isError ? <ErrorState description="The playbook could not be loaded." /> : null}
        {!isLoading && !isError && !playbook ? (
          <EmptyState description="No playbook is attached to this investigation context." title="No playbook" />
        ) : null}

        {playbook ? (
          <>
            <span className="metric-row__label">{playbook.summary}</span>

            <div className="metric-stack">
              <strong>Evidence requirements</strong>
              {playbook.evidence_requirements.length > 0 ? (
                playbook.evidence_requirements.map((requirement) => (
                  <div className="metric-row metric-row--stacked" key={requirement.id}>
                    <strong>{requirement.label}</strong>
                    <span className="metric-row__label">{requirement.description}</span>
                    <span className="metric-row__label">
                      {listLabel(requirement.source_types, 'No source types')}
                    </span>
                    {requirement.required ? <Chip label="Required" tone="warning" /> : null}
                  </div>
                ))
              ) : (
                <EmptyState description="This playbook does not list evidence requirements." title="No requirements" />
              )}
            </div>

            <div className="metric-stack">
              <strong>Workflow steps</strong>
              {playbook.workflow_steps.length > 0 ? (
                playbook.workflow_steps.map((step) => (
                  <div className="metric-row metric-row--stacked" key={step.id}>
                    <strong>{step.label}</strong>
                    <span className="metric-row__label">{step.capability_ref}</span>
                    <span className="metric-row__label">
                      Inputs: {listLabel(step.input_refs, 'none')} · Outputs:{' '}
                      {listLabel(step.output_refs, 'none')}
                    </span>
                    {step.requires_human_approval ? (
                      <Chip label="Human approval required" tone="warning" />
                    ) : null}
                  </div>
                ))
              ) : (
                <EmptyState description="This playbook does not list workflow steps." title="No workflow steps" />
              )}
            </div>

            <div className="metric-stack">
              <strong>RAG prompts</strong>
              {playbook.rag_prompts.length > 0 ? (
                playbook.rag_prompts.map((prompt) => (
                  <div className="metric-row metric-row--stacked" key={prompt.id}>
                    <strong>{prompt.id}</strong>
                    <span className="metric-row__label">
                      {prompt.model_ref} · {prompt.prompt_version}
                    </span>
                  </div>
                ))
              ) : (
                <EmptyState description="This playbook does not list RAG prompts." title="No RAG prompts" />
              )}
            </div>

            <div className="metric-stack">
              <strong>Decision guidance</strong>
              {playbook.decision_guidance.length > 0 ? (
                playbook.decision_guidance.map((guidance) => (
                  <span className="metric-row__label" key={guidance}>
                    {guidance}
                  </span>
                ))
              ) : (
                <EmptyState description="This playbook does not list decision guidance." title="No guidance" />
              )}
            </div>
          </>
        ) : null}
      </div>
    </Card>
  )
}
