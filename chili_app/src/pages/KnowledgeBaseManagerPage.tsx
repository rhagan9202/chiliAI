import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import { useCreateKnowledgeBase, useKnowledgeBase, useKnowledgeBases } from '../api/knowledgebases'
import { KnowledgeBaseSelector } from '../components/ingestion/KnowledgeBaseSelector'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { KbDomainBadge } from '../components/knowledgebase/KbDomainBadge'
import { StatusChip } from '../components/status/StatusChip'
import { formatTimestamp } from '../components/status/formatters'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { AddDataSection } from '../features/kb/add-data/AddDataSection'
import { DataSection } from '../features/kb/data/DataSection'
import { OverviewSection } from '../features/kb/overview/OverviewSection'
import { RunsSection } from '../features/kb/runs/RunsSection'
import { SettingsSection } from '../features/kb/settings/SettingsSection'
import './pages.css'

export function KnowledgeBaseManagerPage() {
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()
  // Honor a ?kb= deep-link as the initial selection, matching the convention on
  // AlertFeedPage / PolicyIntelligencePage / InvestigationWorkbenchPage. If the
  // requested KB isn't in the visible list, the auto-select fallback below wins.
  const [searchParams] = useSearchParams()
  const requestedKnowledgeBaseId = searchParams.get('kb')
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(
    () => requestedKnowledgeBaseId,
  )
  const [knowledgeBaseName, setKnowledgeBaseName] = useState('')
  const [knowledgeBaseDescription, setKnowledgeBaseDescription] = useState('')
  const [showAllDomains, setShowAllDomains] = useState(false)
  // The staging form lives in the main column while the inventory that reports
  // "no documents yet" sits in the aside; the empty state's action has to take
  // the analyst back across the page to it (UXA-305).
  const sourceStepRef = useRef<HTMLDivElement | null>(null)

  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null
  // Default scope: KBs stamped with the active domain plus legacy KBs without a
  // domain stamp (isDomainMismatch never flags a null/undefined KB domain).
  const scopedKnowledgeBases = knowledgeBases.filter(
    (item) => !isDomainMismatch(item.domain ?? null, activeDomainName),
  )
  const hiddenDomainCount = knowledgeBases.length - scopedKnowledgeBases.length
  const visibleKnowledgeBases = showAllDomains ? knowledgeBases : scopedKnowledgeBases
  // Auto-select prefers in-scope KBs; an explicit selection is honored only
  // while its KB is visible, so scoping back down can never leave the run
  // timeline or document inventory pointed at an out-of-scope KB.
  const activeKnowledgeBaseId = visibleKnowledgeBases.some(
    (item) => item.id === selectedKnowledgeBaseId,
  )
    ? selectedKnowledgeBaseId
    : scopedKnowledgeBases[0]?.id ?? visibleKnowledgeBases[0]?.id ?? null
  const knowledgeBaseDetailQuery = useKnowledgeBase(activeKnowledgeBaseId)
  const knowledgeBase = knowledgeBaseDetailQuery.data ?? null

  const createKnowledgeBaseMutation = useCreateKnowledgeBase()

  if (knowledgeBasesQuery.isLoading || domainConfigQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }

  if (knowledgeBasesQuery.isError || domainConfigQuery.isError) {
    return <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
  }

  if (!knowledgeBasesQuery.data || !domainConfigQuery.data) {
    return <LoadingState label="Waiting for knowledge base configuration" />
  }

  if (activeKnowledgeBaseId && knowledgeBaseDetailQuery.isLoading) {
    return <LoadingState label="Loading selected knowledge base" />
  }

  if (knowledgeBaseDetailQuery.isError) {
    return <ErrorState description="This knowledge base could not be opened. Try again, or pick another one." />
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label="Documents + records" tone="info" />}
        eyebrow="Ingestion"
        subtitle="Add documents and structured records to a knowledge base, and check what has already landed in it."
        title="Knowledge Bases"
      />

      <div className="ingestion-studio-layout">
        <div className="ingestion-studio-main">
          <Card>
            <KnowledgeBaseSelector
              activeDomainName={activeDomainName}
              activeKnowledgeBaseId={activeKnowledgeBaseId}
              createDescription={knowledgeBaseDescription}
              createDisabled={createKnowledgeBaseMutation.isPending}
              createName={knowledgeBaseName}
              hiddenDomainCount={hiddenDomainCount}
              knowledgeBases={visibleKnowledgeBases}
              onCreateDescriptionChange={setKnowledgeBaseDescription}
              onCreateNameChange={setKnowledgeBaseName}
              onCreateSubmit={() => {
                createKnowledgeBaseMutation.mutate(
                  {
                    name: knowledgeBaseName.trim(),
                    description: knowledgeBaseDescription.trim(),
                  },
                  {
                    onSuccess: (created) => {
                      setSelectedKnowledgeBaseId(created.id)
                      setKnowledgeBaseName('')
                      setKnowledgeBaseDescription('')
                    },
                  },
                )
              }}
              onSelect={(knowledgeBaseId) => {
                setSelectedKnowledgeBaseId(knowledgeBaseId)
              }}
              onToggleShowAllDomains={() => setShowAllDomains((value) => !value)}
              showAllDomains={showAllDomains}
            />
          </Card>

          {activeKnowledgeBaseId ? (
            // The staging form used to report "no documents yet" via a ref
            // scrolled into view by the empty-inventory action below
            // (UXA-305); AddDataSection owns the form now, so the ref moves
            // to this wrapper instead of the section it used to sit inside.
            <div ref={sourceStepRef}>
              <AddDataSection
                knowledgeBaseId={activeKnowledgeBaseId}
                // The submission's own consequences (clearing the staged draft,
                // invalidating this knowledge base's detail query) already
                // happen inside AddDataSection's flows; the page has nothing
                // left to do here now that OverviewSection reads its situation
                // straight from the (auto-refetched) knowledge base counts.
                onSubmitted={() => undefined}
              />
            </div>
          ) : null}
        </div>

        <aside className="ingestion-studio-context" aria-label="Ingestion context">
          <Card>
            <SelectedKnowledgeBaseSummary
              activeDomainName={activeDomainName}
              knowledgeBase={knowledgeBase}
            />
          </Card>

          {knowledgeBase ? (
            <OverviewSection activeDomainName={activeDomainName} knowledgeBase={knowledgeBase} />
          ) : null}

          {activeKnowledgeBaseId ? (
            <RunsSection
              entityCount={knowledgeBase?.entity_count ?? 0}
              knowledgeBaseId={activeKnowledgeBaseId}
            />
          ) : null}

          {activeKnowledgeBaseId ? (
            <DataSection
              knowledgeBaseId={activeKnowledgeBaseId}
              onStageSource={() => {
                const section = sourceStepRef.current
                if (section && typeof section.scrollIntoView === 'function') {
                  section.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }
              }}
            />
          ) : null}

          {knowledgeBase ? (
            <SettingsSection
              knowledgeBase={knowledgeBase}
              onDeleted={() => setSelectedKnowledgeBaseId(null)}
            />
          ) : null}
        </aside>
      </div>
    </section>
  )
}

function SelectedKnowledgeBaseSummary({
  activeDomainName,
  knowledgeBase,
}: {
  activeDomainName: string | null
  knowledgeBase: NonNullable<ReturnType<typeof useKnowledgeBase>['data']> | null
}) {
  if (!knowledgeBase) {
    return (
      <EmptyState
        description="Create or select a knowledge base before submitting ingestion runs."
        title="No knowledge base selected"
      />
    )
  }

  const kbDomain = knowledgeBase.domain ?? null
  const hasDomainMismatch = isDomainMismatch(kbDomain, activeDomainName)

  return (
    <section className="ingestion-studio-summary" aria-labelledby="selected-kb-title">
      <div className="metric-row">
        <div>
          <strong id="selected-kb-title">{knowledgeBase.name}</strong>
          <p className="page-copy-block">{knowledgeBase.description}</p>
        </div>
        <StatusChip kind="knowledge-base" status={knowledgeBase.status} />
        <KbDomainBadge activeDomainName={activeDomainName} kbDomain={kbDomain} />
      </div>

      {hasDomainMismatch ? (
        <p className="page-copy-block" data-testid="kb-domain-mismatch-note" role="status">
          This knowledge base was created under the &quot;{kbDomain}&quot; domain, but
          &quot;{activeDomainName}&quot; is now active. Its entities and relationships may not
          match the active domain&apos;s configuration. All actions remain available.
        </p>
      ) : null}

      <div className="knowledge-base-stats">
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Documents</span>
          <strong>{knowledgeBase.document_count}</strong>
        </div>
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Entities</span>
          <strong>{knowledgeBase.entity_count}</strong>
        </div>
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Relationships</span>
          <strong>{knowledgeBase.relationship_count}</strong>
        </div>
        <div className="knowledge-base-stat">
          <span className="metric-row__label">Created</span>
          <strong>{formatTimestamp(knowledgeBase.created_at)}</strong>
        </div>
      </div>
    </section>
  )
}
