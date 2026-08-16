import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import { useKnowledgeBases } from '../api/knowledgebases'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { CreateKnowledgeBasePanel } from '../features/kb/library/CreateKnowledgeBasePanel'
import { KnowledgeBaseCardList } from '../features/kb/library/KnowledgeBaseCardList'
import { knowledgeBaseWorkspacePath, legacyWorkspaceRedirect } from '../utils/knowledgeBaseRoutes'
import '../features/kb/kb.css'

/**
 * The library: every knowledge base as an address, plus the way to make one.
 *
 * It holds no notion of a "selected" knowledge base — opening one is
 * navigation into its workspace (spec §1), so the only state here is how wide
 * the domain scope is drawn.
 */
export function KnowledgeBaseLibraryPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [showAllDomains, setShowAllDomains] = useState(false)
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()

  // A pre-split address (`?kb=`, optionally `&document=`) still names a real
  // destination; send it there rather than growing a second way to select.
  const legacyTarget = legacyWorkspaceRedirect(searchParams)
  if (legacyTarget !== null) {
    return <Navigate replace to={legacyTarget} />
  }

  if (knowledgeBasesQuery.isLoading || domainConfigQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }
  if (knowledgeBasesQuery.isError || domainConfigQuery.isError) {
    return (
      <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
    )
  }

  // Domain scoping, lifted from the manager page unchanged: KBs stamped with
  // the active domain, plus legacy KBs with no stamp at all (isDomainMismatch
  // never flags a null domain). Warn-only — the toggle reveals the rest rather
  // than the scoping being enforced.
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null
  const scopedKnowledgeBases = knowledgeBases.filter(
    (item) => !isDomainMismatch(item.domain ?? null, activeDomainName),
  )
  const hiddenDomainCount = knowledgeBases.length - scopedKnowledgeBases.length
  const visibleKnowledgeBases = showAllDomains ? knowledgeBases : scopedKnowledgeBases

  return (
    <section className="page-grid">
      <SectionHeader
        eyebrow="Ingestion"
        subtitle="Pick a knowledge base to work in, or create one."
        title="Knowledge Bases"
      />
      <Card>
        <CreateKnowledgeBasePanel
          // A brand-new corpus has nothing to look at anywhere else, so
          // creating one lands in Add data rather than on an empty overview.
          onCreated={(knowledgeBaseId) => {
            navigate(knowledgeBaseWorkspacePath(knowledgeBaseId, 'add'))
          }}
        />
      </Card>
      <Card>
        <KnowledgeBaseCardList
          activeDomainName={activeDomainName}
          hiddenDomainCount={hiddenDomainCount}
          knowledgeBases={visibleKnowledgeBases}
          onToggleShowAllDomains={() => setShowAllDomains((value) => !value)}
          showAllDomains={showAllDomains}
        />
      </Card>
    </section>
  )
}
