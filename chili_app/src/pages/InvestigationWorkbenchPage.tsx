import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'

import { useAlerts } from '../api/alerts'
import { useRiskScore, useTimeseries } from '../api/analytics'
import { useDomainConfig } from '../api/config'
import type { DomainConfig, RuntimeEntity, RuntimeRelationship } from '../api/contracts'
import { useEvidencePack } from '../api/evidence'
import {
  useInvestigationEntity,
  useInvestigationEntitySearch,
  useInvestigationNeighborhood,
} from '../api/investigation'
import { useKnowledgeBases } from '../api/knowledgebases'
import { TrendBars } from '../components/charts/TrendBars'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { RiskBadge } from '../components/ui/RiskBadge'
import {
  getEntityChips,
  getEntitySubtitle,
  getEntityTitle,
  getEntityTypeLabel,
  getRelationshipTypeLabel,
} from '../utils/domainDisplay'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function InvestigationWorkbenchPage() {
  const { entityId } = useParams()
  const domainConfigQuery = useDomainConfig()
  const knowledgeBasesQuery = useKnowledgeBases()
  const alertsQuery = useAlerts()
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(entityId ?? null)
  const [depth, setDepth] = useState(2)

  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeKnowledgeBaseId = knowledgeBases.some((item) => item.id === selectedKnowledgeBaseId)
    ? selectedKnowledgeBaseId
    : knowledgeBases[0]?.id ?? null

  const searchQuery = useInvestigationEntitySearch(activeKnowledgeBaseId, searchTerm)
  const entityQuery = useInvestigationEntity(activeKnowledgeBaseId, selectedEntityId)
  const neighborhoodQuery = useInvestigationNeighborhood(activeKnowledgeBaseId, selectedEntityId, depth)
  const riskQuery = useRiskScore(selectedEntityId)
  const timeseriesQuery = useTimeseries(selectedEntityId)

  const selectedAlert = useMemo(
    () => alertsQuery.data?.items.find((alert) => alert.entity_id === selectedEntityId) ?? null,
    [alertsQuery.data?.items, selectedEntityId],
  )
  const evidenceQuery = useEvidencePack(selectedAlert?.evidence_pack_id ?? null)

  if (domainConfigQuery.isLoading || knowledgeBasesQuery.isLoading || alertsQuery.isLoading) {
    return <LoadingState label="Loading investigation context" />
  }

  if (domainConfigQuery.isError || knowledgeBasesQuery.isError || alertsQuery.isError) {
    return <ErrorState description="Investigation data could not be loaded from the backend." />
  }

  if (!domainConfigQuery.data || !knowledgeBasesQuery.data || !alertsQuery.data) {
    return <LoadingState label="Waiting for investigation data" />
  }

  if (knowledgeBases.length === 0) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Entity workbench"
          subtitle="Create and ingest a knowledge base before exploring graph entities."
          title="Investigation Workbench"
        />
        <Card>
          <EmptyState
            description="The live investigation workbench queries the graph through a selected knowledge base. Create one on the Knowledge Bases page, upload documents, then return here to search extracted entities."
            title="No graph-ready knowledge base"
          />
        </Card>
      </section>
    )
  }

  const entity = entityQuery.data?.entity ?? null
  const neighborhood = neighborhoodQuery.data ?? null
  const riskScore = riskQuery.data ?? null
  const timeseries = timeseriesQuery.data ?? null
  const entityTitle = entity ? getEntityTitle(entity, domainConfigQuery.data) : 'Investigation Workbench'
  const entitySubtitle = entity ? getEntitySubtitle(entity, domainConfigQuery.data) : null
  const selectedTypeLabel = entity ? getEntityTypeLabel(entity.type, domainConfigQuery.data) : null
  const entityChips = entity ? getEntityChips(entity, domainConfigQuery.data) : []

  return (
    <section className="page-grid">
      <SectionHeader
        actions={selectedAlert ? <Chip label={selectedAlert.severity} tone="warning" /> : undefined}
        eyebrow="Entity workbench"
        subtitle="Search the active knowledge base, load an entity, and inspect its live graph neighborhood through backend graph adapters."
        title={entityTitle}
      />

      <Card>
        <div className="metric-stack">
          <div className="metric-row">
            <label className="metric-row__label" htmlFor="investigation-kb-select">
              Knowledge base
            </label>
            <select
              className="page-input"
              id="investigation-kb-select"
              onChange={(event) => {
                setSelectedKnowledgeBaseId(event.target.value)
                setSelectedEntityId(null)
              }}
              value={activeKnowledgeBaseId ?? ''}
            >
              {knowledgeBases.map((knowledgeBase) => (
                <option key={knowledgeBase.id} value={knowledgeBase.id}>
                  {knowledgeBase.name} · {knowledgeBase.status}
                </option>
              ))}
            </select>
          </div>
          <div className="metric-row">
            <label className="metric-row__label" htmlFor="investigation-search">
              Entity search
            </label>
            <input
              className="page-input"
              id="investigation-search"
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder={`Search ${domainConfigQuery.data.domain.display_name} entities`}
              type="search"
              value={searchTerm}
            />
          </div>
          {searchQuery.isError ? (
            <ErrorState description="Entity search failed for the selected knowledge base." />
          ) : null}
          {searchQuery.data ? (
            <div className="knowledge-base-documents">
              {searchQuery.data.items.length > 0 ? searchQuery.data.items.map((result) => (
                <button
                  className={selectedEntityId === result.id ? 'page-list-item page-list-item--active' : 'page-list-item'}
                  key={result.id}
                  onClick={() => setSelectedEntityId(result.id)}
                  type="button"
                >
                  <strong>{getEntityTitle(result, domainConfigQuery.data)}</strong>
                  <span className="metric-row__label">
                    {getEntityTypeLabel(result.type, domainConfigQuery.data)} · {getEntitySubtitle(result, domainConfigQuery.data) ?? result.id}
                  </span>
                </button>
              )) : (
                <EmptyState description="Try another property value or upload more documents to this knowledge base." title="No matching entities" />
              )}
            </div>
          ) : (
            <EmptyState description="Search by an entity property value, then select a result to load its graph neighborhood." title="Search live graph entities" />
          )}
        </div>
      </Card>

      {entityQuery.isLoading || neighborhoodQuery.isLoading ? <LoadingState label="Loading selected entity graph" /> : null}
      {entityQuery.isError || neighborhoodQuery.isError ? (
        <ErrorState description="The selected entity could not be loaded from the active knowledge base." />
      ) : null}

      {entity ? (
        <>
          <div className="investigation-layout">
            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <span className="metric-row__label">Entity type</span>
                  <Chip label={selectedTypeLabel ?? entity.type} tone="network" />
                </div>
                {riskScore ? (
                  <>
                    <div className="metric-row">
                      <span className="metric-row__label">Composite risk</span>
                      <RiskBadge score={Math.round(riskScore.overall_score * 100)} />
                    </div>
                    <ConfidenceBar value={Math.round(riskScore.overall_score * 100)} />
                  </>
                ) : null}
                <div className="alert-row-card__meta">
                  {entityChips.map((chip) => (
                    <Chip key={chip} label={chip} tone="default" />
                  ))}
                </div>
                <p className="page-copy-block">{entitySubtitle ?? entity.id}</p>
              </div>
            </Card>

            <Card>
              <div className="metric-stack">
                <strong>Risk factors</strong>
                {riskScore ? riskScore.factors.map((factor) => (
                  <div className="metric-row metric-row--stacked" key={factor.factor_name}>
                    <strong>{factor.factor_name.replace(/_/g, ' ')}</strong>
                    <span className="metric-row__label">{factor.rationale ?? 'No rationale provided.'}</span>
                    <ConfidenceBar value={Math.round(factor.contribution * 100)} />
                  </div>
                )) : (
                  <EmptyState description="Risk scoring is unavailable until an entity is selected and analytics respond." title="No risk score" />
                )}
              </div>
            </Card>
          </div>

          <div className="dashboard-panels">
            {timeseries ? <ChartFrameInvestigation timeseries={timeseries.points} /> : null}

            <Card>
              <div className="metric-stack">
                <div className="metric-row">
                  <strong>Graph neighborhood</strong>
                  <label className="metric-row__label" htmlFor="investigation-depth">
                    Depth
                  </label>
                  <select
                    className="page-input"
                    id="investigation-depth"
                    onChange={(event) => setDepth(Number(event.target.value))}
                    value={depth}
                  >
                    {[1, 2, 3, 4, 5].map((value) => (
                      <option key={value} value={value}>{value}</option>
                    ))}
                  </select>
                </div>
                {neighborhood ? (
                  <NeighborhoodList
                    config={domainConfigQuery.data}
                    centerEntityId={entity.id}
                    entities={neighborhood.entities}
                    relationships={neighborhood.relationships}
                  />
                ) : (
                  <EmptyState description="Select an entity to load its graph neighborhood." title="No neighborhood loaded" />
                )}
              </div>
            </Card>
          </div>

          {evidenceQuery.data ? (
            <Card>
              <div className="metric-stack">
                <strong>Evidence pack</strong>
                <p className="page-copy-block">{evidenceQuery.data.reasoning}</p>
                {evidenceQuery.data.items.map((item) => (
                  <div className="metric-row metric-row--stacked" key={item.source_id}>
                    <strong>{item.source_type}</strong>
                    <span className="metric-row__label">{item.quote}</span>
                    <span className="metric-row__label">{item.rationale}</span>
                  </div>
                ))}
              </div>
            </Card>
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function NeighborhoodList({
  centerEntityId,
  config,
  entities,
  relationships,
}: {
  centerEntityId: string
  config: DomainConfig
  entities: RuntimeEntity[]
  relationships: RuntimeRelationship[]
}) {
  const neighbors = entities.filter((item) => item.id !== centerEntityId)

  if (neighbors.length === 0 && relationships.length === 0) {
    return <EmptyState description="The selected entity has no relationships at this depth." title="No connected entities" />
  }

  return (
    <div className="knowledge-base-documents">
      {neighbors.map((neighbor) => (
        <div className="metric-row metric-row--stacked" key={neighbor.id}>
          <strong>{getEntityTitle(neighbor, config)}</strong>
          <span className="metric-row__label">
            {getEntityTypeLabel(neighbor.type, config)} · {getEntitySubtitle(neighbor, config) ?? neighbor.id}
          </span>
        </div>
      ))}
      {relationships.map((relationship) => (
        <div className="metric-row metric-row--stacked" key={relationship.id}>
          <strong>{getRelationshipTypeLabel(relationship.type, config)}</strong>
          <span className="metric-row__label">{relationship.source_id} → {relationship.target_id}</span>
        </div>
      ))}
    </div>
  )
}

function ChartFrameInvestigation({
  timeseries,
}: {
  timeseries: { label: string; value: number; is_anomaly: boolean }[]
}) {
  return (
    <Card>
      <div className="metric-stack">
        <strong>Risk pressure trend</strong>
        <div className="chart-shell">
          <TrendBars
            color="#00d4ff"
            data={timeseries.map((point) => ({ label: point.label, value: Number(point.value.toFixed(2)) }))}
          />
        </div>
        <div className="alert-row-card__meta">
          {timeseries.filter((point) => point.is_anomaly).map((point) => (
            <Chip key={point.label} label={`${point.label} anomaly`} tone="danger" />
          ))}
        </div>
      </div>
    </Card>
  )
}