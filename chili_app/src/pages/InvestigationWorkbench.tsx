import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

import { EntityDetailPanel } from '../components/investigation/EntityDetailPanel'
import { EvidencePanel } from '../components/investigation/EvidencePanel'
import { TimelinePanel } from '../components/investigation/TimelinePanel'
import { useDomainConfig } from '../hooks/useDomainConfig'
import { useEntity } from '../hooks/useEntity'
import { useEntitySearch } from '../hooks/useEntitySearch'
import { useKnowledgeBases } from '../hooks/useKnowledgeBases'
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
  const [searchText, setSearchText] = useState('')
  const [submittedSearch, setSubmittedSearch] = useState('')

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
  const knowledgeBases = useKnowledgeBases()
  const entitySearch = useEntitySearch(activeKnowledgeBaseId, submittedSearch)

  const neighborhood = useNeighborhood(
    selectedEntityId,
    activeKnowledgeBaseId,
    NEIGHBORHOOD_DEPTH,
  )
  const entity = useEntity(selectedEntityId, activeKnowledgeBaseId)

  const subgraph: SubgraphResult =
    neighborhood.data?.subgraph ?? EMPTY_SUBGRAPH

  const handleKnowledgeBaseChange = (
    event: ChangeEvent<HTMLSelectElement>,
  ): void => {
    const nextKbId = event.target.value || null
    setActiveKnowledgeBase(nextKbId)
    selectEntity(null)
    setSubmittedSearch('')
    setSearchText('')
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (nextKbId) {
          next.set('kb_id', nextKbId)
        } else {
          next.delete('kb_id')
        }
        next.delete('entity_id')
        return next
      },
      { replace: true },
    )
  }

  const handleSearchSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    setSubmittedSearch(searchText.trim())
  }

  const handleSelectSearchResult = (entityId: string): void => {
    selectEntity(entityId)
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (activeKnowledgeBaseId) {
          next.set('kb_id', activeKnowledgeBaseId)
        }
        next.set('entity_id', entityId)
        return next
      },
      { replace: true },
    )
  }

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
      <form
        aria-label="Entity discovery"
        onSubmit={handleSearchSubmit}
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(180px, 260px) minmax(220px, 1fr) auto',
          gap: 8,
          alignItems: 'end',
          marginBottom: 12,
        }}
      >
        <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
          Knowledge base
          <select
            aria-label="Knowledge base"
            value={activeKnowledgeBaseId ?? ''}
            onChange={handleKnowledgeBaseChange}
            disabled={knowledgeBases.isLoading}
          >
            <option value="">Select a knowledge base</option>
            {(knowledgeBases.data?.items ?? []).map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 4, fontSize: 13 }}>
          Entity search
          <input
            aria-label="Entity search"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search graph properties, e.g. NPI, claim, facility"
            disabled={!activeKnowledgeBaseId}
          />
        </label>
        <button
          type="submit"
          disabled={!activeKnowledgeBaseId || searchText.trim().length === 0}
        >
          Search
        </button>
      </form>
      {entitySearch.isError && (
        <div
          role="alert"
          style={{
            padding: 12,
            border: '1px solid #fecaca',
            background: '#fef2f2',
            borderRadius: 8,
            color: '#b91c1c',
            fontSize: 13,
            marginBottom: 12,
          }}
        >
          Entity search failed: {entitySearch.error.message}
        </div>
      )}
      {submittedSearch && entitySearch.data && (
        <div
          aria-label="Entity search results"
          style={{
            border: '1px solid var(--border, #e5e4e7)',
            borderRadius: 8,
            padding: 12,
            marginBottom: 12,
            background: 'var(--bg-soft, #faf8fc)',
          }}
        >
          <strong style={{ display: 'block', marginBottom: 8 }}>
            {entitySearch.data.total} result(s)
          </strong>
          {entitySearch.data.items.length === 0 ? (
            <span style={{ fontSize: 13, color: 'var(--text, #6b6375)' }}>
              No entities matched “{submittedSearch}”.
            </span>
          ) : (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {entitySearch.data.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleSelectSearchResult(item.id)}
                >
                  {item.type}: {String(Object.values(item.properties)[0] ?? item.id)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 360px',
          gap: 16,
          alignItems: 'stretch',
          height: 'calc(100vh - 160px)',
          minHeight: 480,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'relative',
            minWidth: 0,
            minHeight: 0,
            height: '100%',
            overflow: 'hidden',
          }}
        >
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
            minHeight: 0,
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
