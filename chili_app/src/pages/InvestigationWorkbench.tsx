import { Suspense, lazy, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { EntityDetailPanel } from '../components/investigation/EntityDetailPanel'
import { EvidencePanel } from '../components/investigation/EvidencePanel'
import { TimelinePanel } from '../components/investigation/TimelinePanel'
import { useDomainConfig } from '../hooks/useDomainConfig'
import { useEntity } from '../hooks/useEntity'
import { useNeighborhood } from '../hooks/useNeighborhood'
import { useAppStore } from '../stores/appStore'
import type { SubgraphResult } from '../types/api'

const GraphCanvas = lazy(async () => {
  const mod = await import('../components/investigation/GraphCanvas')
  return { default: mod.GraphCanvas }
})

const NEIGHBORHOOD_DEPTH = 2
const EMPTY_SUBGRAPH: SubgraphResult = { nodes: [], edges: [] }

export function InvestigationWorkbench(): React.ReactElement {
  const [searchParams, setSearchParams] = useSearchParams()
  const config = useDomainConfig()

  const selectedEntityId = useAppStore((state) => state.selectedEntityId)
  const selectEntity = useAppStore((state) => state.selectEntity)
  const activeKnowledgeBaseId = useAppStore(
    (state) => state.activeKnowledgeBaseId,
  )
  const setActiveKnowledgeBase = useAppStore(
    (state) => state.setActiveKnowledgeBase,
  )

  const urlEntityId = searchParams.get('entity_id')
  const urlKbId = searchParams.get('kb_id')

  // Seed Zustand from URL on mount only — subsequent URL changes from inside
  // this page are driven by the store, so re-syncing would create a loop.
  useEffect(() => {
    if (urlEntityId && useAppStore.getState().selectedEntityId === null) {
      selectEntity(urlEntityId)
    }
    if (urlKbId && useAppStore.getState().activeKnowledgeBaseId === null) {
      setActiveKnowledgeBase(urlKbId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!selectedEntityId) return
    setSearchParams(
      (prev) => {
        if (prev.get('entity_id') === selectedEntityId) return prev
        const next = new URLSearchParams(prev)
        next.set('entity_id', selectedEntityId)
        if (activeKnowledgeBaseId && !next.has('kb_id')) {
          next.set('kb_id', activeKnowledgeBaseId)
        }
        return next
      },
      { replace: true },
    )
  }, [selectedEntityId, activeKnowledgeBaseId, setSearchParams])

  const entityTypes = useMemo(
    () => config.entities.map((entity) => entity.name),
    [config.entities],
  )

  const neighborhood = useNeighborhood(
    selectedEntityId,
    activeKnowledgeBaseId,
    NEIGHBORHOOD_DEPTH,
  )
  const entity = useEntity(selectedEntityId, activeKnowledgeBaseId)

  const subgraph: SubgraphResult =
    neighborhood.data?.subgraph ?? EMPTY_SUBGRAPH

  return (
    <section className="investigation-workbench">
      <header
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          marginBottom: 12,
        }}
      >
        <h1 style={{ margin: 0, fontSize: 20 }}>Investigation Workbench</h1>
        <p
          style={{
            margin: 0,
            fontSize: 13,
            color: 'var(--text, #6b6375)',
          }}
        >
          Explore entities and their neighborhoods. Click a node to inspect
          details, evidence, and timeline.
        </p>
      </header>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 360px',
          gap: 16,
          alignItems: 'stretch',
          height: 'calc(100vh - 160px)',
          minHeight: 480,
        }}
      >
        <div style={{ position: 'relative', minWidth: 0 }}>
          {!activeKnowledgeBaseId && (
            <div
              style={{
                padding: 16,
                border: '1px solid var(--border, #e5e4e7)',
                borderRadius: 8,
                fontSize: 13,
                color: 'var(--text, #6b6375)',
                background: 'var(--bg-soft, #faf8fc)',
                marginBottom: 12,
              }}
              role="status"
            >
              No knowledge base selected. Add{' '}
              <code>?kb_id=&lt;id&gt;</code> (and optionally{' '}
              <code>&amp;entity_id=&lt;id&gt;</code>) to the URL or set the
              active KB to begin.
            </div>
          )}
          {neighborhood.isError && (
            <div
              style={{
                padding: 12,
                border: '1px solid #fecaca',
                background: '#fef2f2',
                borderRadius: 8,
                color: '#b91c1c',
                fontSize: 13,
                marginBottom: 12,
              }}
              role="alert"
            >
              Failed to load neighborhood: {neighborhood.error.message}
            </div>
          )}
          <Suspense
            fallback={
              <div
                style={{
                  padding: 24,
                  fontSize: 13,
                  color: 'var(--text, #6b6375)',
                }}
              >
                Loading graph…
              </div>
            }
          >
            <GraphCanvas
              subgraph={subgraph}
              selectedEntityId={selectedEntityId}
              centerEntityId={
                neighborhood.data?.centerEntityId ?? selectedEntityId
              }
              onSelectNode={(id) => selectEntity(id)}
              entityTypes={entityTypes}
            />
          </Suspense>
        </div>
        <aside
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            overflowY: 'auto',
            minWidth: 0,
          }}
        >
          <EntityDetailPanel
            entity={entity.data ?? null}
            isLoading={entity.isLoading && Boolean(selectedEntityId)}
            isError={entity.isError}
            errorMessage={entity.error?.message}
          />
          <EvidencePanel
            entityId={selectedEntityId}
            evidence={[]}
            isLoading={false}
            isError={false}
          />
          <TimelinePanel entity={entity.data ?? null} />
        </aside>
      </div>
    </section>
  )
}

export default InvestigationWorkbench
