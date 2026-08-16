import { Link, Outlet, useParams } from 'react-router'

import type { KnowledgeBaseSummaryResponse } from '../api/contracts'
import { useDomainConfig } from '../api/config'
import { useKnowledgeBase } from '../api/knowledgebases'
import { KbDomainBadge } from '../components/knowledgebase/KbDomainBadge'
import { StatusChip } from '../components/status/StatusChip'
import { Chip } from '../components/ui/Chip'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { WorkspaceTabs } from '../features/kb/WorkspaceTabs'
import { countLabel } from '../utils/countLabel'
import { KNOWLEDGE_BASES_ROUTE } from '../utils/knowledgeBaseRoutes'
import '../features/kb/kb.css'

/** What every workspace section route reads instead of re-fetching the KB. */
export type WorkspaceOutletContext = {
  knowledgeBase: KnowledgeBaseSummaryResponse
  activeDomainName: string | null
}

/**
 * The per-knowledge-base workspace: identity and digest at the top, section
 * navigation under it, and the addressed section in the outlet.
 *
 * The knowledge base is loaded once here so the sections below agree on which
 * corpus they are describing — the URL names it, so there is nothing to select.
 */
export function KnowledgeBaseWorkspacePage() {
  const { kbId } = useParams<'kbId'>()
  const knowledgeBaseQuery = useKnowledgeBase(kbId ?? null)
  const domainConfigQuery = useDomainConfig()

  if (!kbId) {
    return <ErrorState description="This address does not name a knowledge base." />
  }
  if (knowledgeBaseQuery.isLoading) {
    return <LoadingState label="Loading knowledge base" />
  }
  if (knowledgeBaseQuery.isError || !knowledgeBaseQuery.data) {
    // A deleted or mistyped id: say so and offer the library, rather than
    // silently swapping in a different corpus.
    return (
      <section className="page-grid">
        <ErrorState description="This knowledge base could not be opened. It may have been deleted. Return to the library to pick another." />
        <p>
          <Link to={KNOWLEDGE_BASES_ROUTE}>Back to knowledge bases</Link>
        </p>
      </section>
    )
  }

  const knowledgeBase = knowledgeBaseQuery.data
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null
  const outletContext: WorkspaceOutletContext = { knowledgeBase, activeDomainName }

  return (
    <section className="page-grid">
      <header className="kb-workspace__header">
        <div className="kb-workspace__identity">
          <h1>{knowledgeBase.name}</h1>
          <p className="page-copy-block">{knowledgeBase.description}</p>
        </div>
        <div className="kb-workspace__digest">
          <StatusChip kind="knowledge-base" status={knowledgeBase.status} />
          <Chip label={countLabel(knowledgeBase.document_count, 'document')} tone="default" />
          <Chip
            label={countLabel(knowledgeBase.entity_count, 'entity', 'entities')}
            tone="network"
          />
          <KbDomainBadge
            activeDomainName={activeDomainName}
            kbDomain={knowledgeBase.domain ?? null}
          />
        </div>
      </header>
      <WorkspaceTabs knowledgeBaseId={kbId} />
      <Outlet context={outletContext} />
    </section>
  )
}
