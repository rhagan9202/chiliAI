import { Link } from 'react-router'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { isDomainMismatch } from '../../../components/knowledgebase/domainMismatch'
import { Card } from '../../../components/ui/Card'
import { countLabel } from '../../../utils/countLabel'
import { knowledgeBaseWorkspacePath } from '../../../utils/knowledgeBaseRoutes'

/**
 * One sentence about where this knowledge base actually stands.
 *
 * Not a status word: the three states a corpus is genuinely in — nothing in
 * it, something in it that produced nothing, something in it that answers
 * questions — need different next actions, and the sentence is what tells them
 * apart before the buttons do.
 */
export function knowledgeBaseSituation(knowledgeBase: KnowledgeBaseSummaryResponse): string {
  if (knowledgeBase.document_count === 0 && knowledgeBase.entity_count === 0) {
    return 'This knowledge base is empty. Add documents or structured records to start.'
  }
  if (knowledgeBase.entity_count === 0) {
    const verb = knowledgeBase.document_count === 1 ? 'is' : 'are'
    return `${countLabel(knowledgeBase.document_count, 'document')} ${verb} ingested but produced no entities yet. Check the runs for extraction problems.`
  }
  return `${countLabel(knowledgeBase.entity_count, 'entity', 'entities')} and ${countLabel(
    knowledgeBase.relationship_count,
    'relationship',
  )} from ${countLabel(knowledgeBase.document_count, 'document')} are ready to investigate.`
}

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
