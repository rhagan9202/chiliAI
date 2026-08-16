import { Link } from 'react-router'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { isDomainMismatch } from '../../../components/knowledgebase/domainMismatch'
import { Card } from '../../../components/ui/Card'
import { knowledgeBaseWorkspacePath } from '../../../utils/knowledgeBaseRoutes'
import { knowledgeBaseSituation } from './knowledgeBaseSituation'

type OverviewSectionProps = {
  knowledgeBase: KnowledgeBaseSummaryResponse
  activeDomainName: string | null
}

type Handoff = { label: string; to: string }

export function OverviewSection({ activeDomainName, knowledgeBase }: OverviewSectionProps) {
  const scope = `?kb=${encodeURIComponent(knowledgeBase.id)}`
  const handoffs: Handoff[] = [
    { label: 'Investigate entities', to: `/investigation${scope}` },
    { label: 'Review alerts', to: `/alerts${scope}` },
    { label: 'Ask in RAG chat', to: `/rag-chat${scope}` },
  ]
  const handoffsAvailable = knowledgeBase.entity_count > 0
  const kbDomain = knowledgeBase.domain ?? null
  const hasDomainMismatch = isDomainMismatch(kbDomain, activeDomainName)

  return (
    <Card>
      <section aria-labelledby="kb-overview-title" className="kb-overview">
        <h2 id="kb-overview-title">Where this knowledge base stands</h2>
        <p className="page-copy-block">{knowledgeBaseSituation(knowledgeBase)}</p>

        {hasDomainMismatch ? (
          <p className="page-copy-block" data-testid="kb-domain-mismatch-note" role="status">
            This knowledge base was created under the &quot;{kbDomain}&quot; domain, but
            &quot;{activeDomainName}&quot; is now active. Its entities and relationships may
            not match the active domain&apos;s configuration. All actions remain available.
          </p>
        ) : null}

        <div className="kb-overview__actions">
          <Link
            className="page-button page-button--primary"
            to={knowledgeBaseWorkspacePath(knowledgeBase.id, 'add')}
          >
            Add data
          </Link>
          {handoffs.map((handoff) =>
            handoffsAvailable ? (
              <Link
                className="page-button page-button--secondary"
                key={handoff.label}
                to={handoff.to}
              >
                {handoff.label}
              </Link>
            ) : (
              // A disabled destination is a button, not a link: there is
              // nowhere to go. Its reason renders below, not in a tooltip.
              <button
                className="page-button page-button--secondary"
                disabled
                key={handoff.label}
                type="button"
              >
                {handoff.label}
              </button>
            ),
          )}
        </div>

        {handoffsAvailable ? null : (
          <p className="page-copy-block">
            Investigating needs at least one extracted entity.
          </p>
        )}
      </section>
    </Card>
  )
}
