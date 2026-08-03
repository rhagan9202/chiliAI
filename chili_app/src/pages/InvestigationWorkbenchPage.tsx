import type { ReactNode } from 'react'
import { useCallback, useMemo, useState } from 'react'

import type { RuntimeEntity } from '../api/contracts'
import type { Entity as ApiEntity } from '../types/api'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { useAlerts } from '../api/alerts'
import { useGnnClusters, useRiskScore, useTimeseries } from '../api/analytics'
import { useCase } from '../api/cases'
import { useDomainConfig, useDomainFeatures } from '../api/config'
import { useEvidencePack } from '../api/evidence'
import { useEntityFeatureValues, useFeatureCatalog } from '../api/features'
import {
  useEntityLocations,
  useInvestigationEntity,
  useInvestigationEntitySearch,
  useInvestigationNeighborhood,
} from '../api/investigation'
import { FeatureList } from '../components/analytics/FeatureList'
import { AnomalyTrendPanel } from '../components/investigation/AnomalyTrendPanel'
import { ClusterMembershipPanel } from '../components/investigation/ClusterMembershipPanel'
import { EntityDossierHeader } from '../components/investigation/EntityDossierHeader'
import { EntityNotHere } from '../components/investigation/EntityNotHere'
import { EntityPolicyPanel } from '../components/investigation/EntityPolicyPanel'
import { EmptyKnowledgeBaseNotice } from '../components/knowledgebase/EmptyKnowledgeBaseNotice'
import { EvidencePackActions } from '../components/investigation/EvidencePackActions'
import { EvidencePackViewer } from '../components/investigation/EvidencePackViewer'
import { GraphCanvas } from '../components/investigation/GraphCanvas'
import { SignalBand } from '../components/investigation/SignalBand'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { ConfidenceBar } from '../components/ui/ConfidenceBar'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { Tabs } from '../components/ui/Tabs'
import { buildRagChatUrl, DEFAULT_RISK_QUESTION } from '../lib/ragContext'
import {
  getEntitySubtitle,
  getEntityTitle,
  getEntityTypeLabel,
} from '../utils/domainDisplay'
import { useActiveKnowledgeBase } from '../hooks/useActiveKnowledgeBase'
import { knowledgeBaseOptionLabel } from '../utils/knowledgeBaseStatus'
import { severityTone } from '../utils/severity'
import { toSubgraphResult } from '../utils/subgraph'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

function WorkbenchTabPanel({ children, tabId }: { children: ReactNode; tabId: string }) {
  return (
    <div
      aria-labelledby={`workbench-tab-${tabId}`}
      className="fade-up"
      id={`workbench-tabpanel-${tabId}`}
      role="tabpanel"
    >
      {children}
    </div>
  )
}

function CockpitStateItem({
  isLoading = false,
  label,
  unavailable = false,
  value,
}: {
  isLoading?: boolean
  label: string
  unavailable?: boolean
  value: string
}) {
  const resolvedValue = isLoading ? 'Loading...' : value
  return (
    <div className="metric-row metric-row--stacked">
      <span className="metric-row__label">{label}</span>
      <strong>{resolvedValue}</strong>
      {unavailable ? (
        <span className="metric-row__label">Requested context could not be loaded.</span>
      ) : null}
    </div>
  )
}

export function InvestigationWorkbenchPage() {
  const { entityId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const domainConfigQuery = useDomainConfig()
  const featuresQuery = useDomainFeatures()
  const {
    activeKnowledgeBaseId,
    knowledgeBases,
    isLoading: knowledgeBasesLoading,
    isError: knowledgeBasesError,
  } = useActiveKnowledgeBase()
  const [searchTerm, setSearchTerm] = useState('')
  const [activeTabId, setActiveTabId] = useState('signals')
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null)
  const selectedEntityId = entityId ?? null
  const depth = depthFromSearchParams(searchParams)
  const requestedAlertId = searchParams.get('alert') || null
  const requestedCaseId = searchParams.get('case') || null
  const requestedEvidencePackId = searchParams.get('evidence') || null

  const alertsQuery = useAlerts({ knowledgeBaseId: activeKnowledgeBaseId ?? undefined })
  const caseQuery = useCase(activeKnowledgeBaseId, requestedCaseId)
  const searchQuery = useInvestigationEntitySearch(activeKnowledgeBaseId, searchTerm)
  const entityQuery = useInvestigationEntity(activeKnowledgeBaseId, selectedEntityId)
  const neighborhoodQuery = useInvestigationNeighborhood(activeKnowledgeBaseId, selectedEntityId, depth)
  const riskQuery = useRiskScore(activeKnowledgeBaseId, selectedEntityId)
  const timeseriesQuery = useTimeseries(activeKnowledgeBaseId, selectedEntityId)
  const gnnClustersQuery = useGnnClusters(activeKnowledgeBaseId)
  const featureCatalogQuery = useFeatureCatalog(activeKnowledgeBaseId)
  const featureValuesQuery = useEntityFeatureValues(
    activeKnowledgeBaseId,
    entityQuery.data?.entity?.type ?? null,
    selectedEntityId,
  )

  const {
    fallbackAlert,
    requestedAlertInvalid,
    selectedAlert,
  } = useMemo(() => {
    const items = alertsQuery.data?.items ?? []
    const explicitAlert = requestedAlertId
      ? items.find(
          (alert) =>
            alert.id === requestedAlertId &&
            alert.entity_id === selectedEntityId &&
            alert.knowledge_base_id === activeKnowledgeBaseId,
        )
      : null
    const nextFallbackAlert = items.find((alert) => alert.entity_id === selectedEntityId) ?? null
    return {
      fallbackAlert: nextFallbackAlert,
      requestedAlertInvalid: Boolean(requestedAlertId) && !explicitAlert,
      selectedAlert: requestedAlertId ? explicitAlert ?? null : nextFallbackAlert,
    }
  }, [activeKnowledgeBaseId, alertsQuery.data?.items, requestedAlertId, selectedEntityId])
  // Stable across renders so the force layout is not rebuilt on every paint.
  const domainConfig = domainConfigQuery.data ?? null
  const labelForNode = useCallback(
    (node: ApiEntity) =>
      domainConfig ? getEntityTitle(node as unknown as RuntimeEntity, domainConfig) : node.id,
    [domainConfig],
  )
  const candidateEvidencePackId =
    requestedEvidencePackId ??
    selectedAlert?.evidence_pack_id ??
    caseQuery.data?.case.evidence_pack_id ??
    caseQuery.data?.evidence_pack?.id ??
    null
  const evidenceQuery = useEvidencePack(candidateEvidencePackId, activeKnowledgeBaseId)
  const requestedCaseInvalid =
    Boolean(requestedCaseId) &&
    !caseQuery.isLoading &&
    (caseQuery.isError ||
      !caseQuery.data?.case ||
      caseQuery.data.case.knowledge_base_id !== activeKnowledgeBaseId ||
      (selectedAlert ? !(caseQuery.data.case.alert_ids ?? []).includes(selectedAlert.id) : false))
  const requestedEvidenceInvalid =
    Boolean(candidateEvidencePackId) &&
    !evidenceQuery.isLoading &&
    (evidenceQuery.isError ||
      (requestedEvidencePackId ? !evidenceQuery.data || evidenceQuery.data.id !== requestedEvidencePackId : false) ||
      (selectedAlert && evidenceQuery.data ? evidenceQuery.data.alert_id !== selectedAlert.id : false))
  const selectedEvidencePackId = requestedEvidenceInvalid
    ? null
    : candidateEvidencePackId
  const ragCaseId = requestedCaseInvalid ? null : caseQuery.data?.case.id ?? null
  const ragEvidencePackId = requestedEvidenceInvalid
    ? null
    : requestedEvidencePackId
      ? evidenceQuery.data?.id ?? null
      : selectedEvidencePackId
  const entityLoadFailed = entityQuery.isError || neighborhoodQuery.isError
  // Asked only once the active KB has already failed to produce the entity.
  const entityLocationsQuery = useEntityLocations(selectedEntityId, entityLoadFailed)

  if (domainConfigQuery.isLoading || knowledgeBasesLoading || alertsQuery.isLoading) {
    return <LoadingState label="Loading investigation context" />
  }

  if (domainConfigQuery.isError || knowledgeBasesError || alertsQuery.isError) {
    return <ErrorState description="This investigation could not be loaded. Try again, or search for another entity." />
  }

  if (!domainConfigQuery.data || !alertsQuery.data) {
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
            action={
              <button
                className="page-button"
                onClick={() => navigate('/knowledge-bases')}
                type="button"
              >
                + Create Knowledge Base
              </button>
            }
            description="Investigation queries the graph through a selected knowledge base. Create one, upload documents, and return here to search extracted entities."
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
  const riskAvailability = analyticsAvailability(riskScore)
  const timeseriesAvailability = analyticsAvailability(timeseries)
  const entityTitle = entity ? getEntityTitle(entity, domainConfigQuery.data) : 'Investigation Workbench'
  const capabilities = featuresQuery.data?.capabilities
  const clusters = gnnClustersQuery.data?.clusters ?? []
  const selectedCluster = clusters.find((cluster) => cluster.cluster_id === selectedClusterId) ?? null
  const clusterMode = Boolean(capabilities?.gnn) && clusters.length > 0

  const tabs = [
    ...(capabilities?.risk_scoring || capabilities?.timeseries ? [{ id: 'signals', label: 'Signals' }] : []),
    { id: 'network', label: 'Network' },
    ...(capabilities?.explainability ? [{ id: 'policy', label: 'Policy' }, { id: 'evidence', label: 'Evidence' }] : []),
  ]
  const resolvedActiveTabId = tabs.some((tab) => tab.id === activeTabId) ? activeTabId : tabs[0].id

  // Distinct subjects the queue has already flagged, newest first, as opening
  // moves for an analyst who does not know the corpus yet.
  const suggestedSubjects = Array.from(
    new Map(
      (alertsQuery.data?.items ?? [])
        .filter((alert) => alert.knowledge_base_id === activeKnowledgeBaseId)
        .map((alert) => [alert.entity_id, alert]),
    ).values(),
  ).slice(0, 5)

  const navigateToEntity = (nextId: string) => {
    const nextSearch = new URLSearchParams(searchParams)
    if (activeKnowledgeBaseId) {
      nextSearch.set('kb', activeKnowledgeBaseId)
    }
    if (!selectedAlert || selectedAlert.entity_id !== nextId) {
      nextSearch.delete('alert')
      nextSearch.delete('evidence')
      nextSearch.delete('case')
    }
    navigate(
      { pathname: `/investigation/${nextId}`, search: nextSearch.toString() },
      { preventScrollReset: true },
    )
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={selectedAlert ? <Chip label={selectedAlert.severity} tone={severityTone(selectedAlert.severity)} /> : undefined}
        eyebrow="Entity workbench"
        subtitle="Follow one subject through its connections: who it deals with, how often, and what the risk and policy signals say."
        title={entityTitle}
      />

      <EmptyKnowledgeBaseNotice
        knowledgeBase={knowledgeBases.find((kb) => kb.id === activeKnowledgeBaseId) ?? null}
      />

      <div className="workbench-layout">
        <div className="workbench-rail">
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
                  const nextSearch = new URLSearchParams(searchParams)
                  nextSearch.set('kb', event.target.value)
                  nextSearch.delete('alert')
                  nextSearch.delete('case')
                  nextSearch.delete('evidence')
                  navigate({ pathname: '/investigation', search: nextSearch.toString() })
                }}
                  value={activeKnowledgeBaseId ?? ''}
                >
                  {knowledgeBases.map((knowledgeBase) => (
                    <option key={knowledgeBase.id} value={knowledgeBase.id}>
                      {knowledgeBaseOptionLabel(knowledgeBase, knowledgeBases)}
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
                      onClick={() => navigateToEntity(result.id)}
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
                <div className="metric-stack">
                  <EmptyState
                    description="Search by a property value, or start from something already flagged."
                    title="Pick a subject to investigate"
                  />
                  {/* The landing state was a bare search box against an
                      unfamiliar corpus (UXA-305). These come from the alerts
                      already loaded on this page — no new endpoint. */}
                  {suggestedSubjects.length > 0 ? (
                    <div aria-label="Flagged subjects" role="group">
                      <span className="filter-group__label">Flagged subjects</span>
                      {suggestedSubjects.map((subject) => (
                        <button
                          className="page-list-item"
                          key={subject.entity_id}
                          onClick={() => navigateToEntity(subject.entity_id)}
                          type="button"
                        >
                          <strong>{subject.entity_label || subject.entity_id}</strong>
                          <span className="metric-row__label">
                            {subject.severity} · {subject.entity_id}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="metric-stack">
          {entityQuery.isLoading || neighborhoodQuery.isLoading ? <LoadingState label="Loading selected entity graph" /> : null}
          {/* "It is somewhere else" and "it does not exist" are different
              answers; the old generic frame gave neither (UXA-104). */}
          {entityLoadFailed && selectedEntityId ? (
            <EntityNotHere
              entityId={selectedEntityId}
              isResolving={entityLocationsQuery.isLoading}
              locations={entityLocationsQuery.data?.items ?? []}
            />
          ) : null}

          {entity ? (
            <>
              <EntityDossierHeader
                config={domainConfigQuery.data}
                entity={entity}
                key={entity.id}
                onAskAi={() =>
                  navigate(buildRagChatUrl({
                    knowledgeBaseId: activeKnowledgeBaseId,
                    source: 'entity',
                    entityId: selectedEntityId,
                    alertId: selectedAlert?.id,
                    caseId: ragCaseId,
                    evidencePackId: ragEvidencePackId,
                    question: DEFAULT_RISK_QUESTION,
                  }))
                }
                riskScore={riskAvailability.unavailable ? null : riskScore}
                riskUnavailableReason={riskAvailability.reason}
              />

              <SignalBand factors={riskAvailability.unavailable ? [] : riskScore?.factors ?? []} />

              <Card compact>
                <div aria-label="Cockpit state" className="metric-stack">
                  <div className="metric-row">
                    <strong>Cockpit state</strong>
                    <span className="metric-row__label">Shareable investigation URL</span>
                  </div>
                  <div className="dashboard-panels">
                    <CockpitStateItem
                      label="Knowledge base"
                      value={activeKnowledgeBaseId ?? 'Not selected'}
                    />
                    <CockpitStateItem
                      label="Entity"
                      value={selectedEntityId ?? 'No entity selected'}
                    />
                    <CockpitStateItem
                      label="Alert"
                      value={
                        selectedAlert?.id ??
                        requestedAlertId ??
                        fallbackAlert?.id ??
                        'No alert selected'
                      }
                      unavailable={requestedAlertInvalid}
                    />
                    <CockpitStateItem
                      isLoading={caseQuery.isLoading}
                      label="Case"
                      value={caseQuery.data?.case.title ?? requestedCaseId ?? 'No case selected'}
                      unavailable={requestedCaseInvalid}
                    />
                    <CockpitStateItem
                      isLoading={evidenceQuery.isLoading}
                      label="Evidence"
                      value={candidateEvidencePackId ?? 'No evidence selected'}
                      unavailable={requestedEvidenceInvalid}
                    />
                  </div>
                </div>
              </Card>

              {tabs.length > 1 ? (
                <div className="page-toolbar">
                  <Tabs
                    activeTabId={resolvedActiveTabId}
                    ariaControlsPrefix="workbench-tabpanel"
                    idPrefix="workbench-tab"
                    onChange={setActiveTabId}
                    tabs={tabs}
                  />
                </div>
              ) : null}

              {resolvedActiveTabId === 'signals' ? (
                <WorkbenchTabPanel key="signals" tabId="signals">
                  <div className="dashboard-panels">
                    {capabilities?.timeseries ? (
                      <AnomalyTrendPanel
                        entitySelected={Boolean(entity)}
                        timeseries={timeseriesAvailability.unavailable ? null : timeseries}
                        unavailableReason={timeseriesAvailability.reason}
                      />
                    ) : null}

                    <Card>
                      <div className="metric-stack">
                        <strong>Risk factors</strong>
                        {riskScore && !riskAvailability.unavailable ? riskScore.factors.map((factor) => (
                          <div className="metric-row metric-row--stacked" key={factor.factor_name}>
                            <strong>{factor.factor_name.replace(/_/g, ' ')}</strong>
                            <span className="metric-row__label">{factor.rationale ?? 'No rationale provided.'}</span>
                            <ConfidenceBar value={Math.round(factor.contribution * 100)} />
                          </div>
                        )) : (
                          // The reason is stated once, in the dossier header
                          // beside the badge it qualifies. Repeating it here
                          // (and again as this panel's title) is what made one
                          // screen say it three times (UXA-305).
                          <EmptyState
                            action={
                              <Link
                                className="page-button page-button--sm"
                                to={`/knowledge-bases?kb=${encodeURIComponent(activeKnowledgeBaseId ?? '')}`}
                              >
                                Add data to this knowledge base
                              </Link>
                            }
                            description="Risk factors appear once analytics have scored this entity."
                            title="No risk factors"
                          />
                        )}
                      </div>
                    </Card>

                    <Card>
                      <div className="metric-stack">
                        <strong>Feature values</strong>
                        {featureValuesQuery.isError || featureCatalogQuery.isError ? (
                          <ErrorState description="Feature values could not be loaded for this entity." />
                        ) : featureValuesQuery.isLoading || featureCatalogQuery.isLoading ? (
                          <LoadingState label="Loading feature values" />
                        ) : (
                          <FeatureList
                            catalog={featureCatalogQuery.data ?? null}
                            values={featureValuesQuery.data?.items ?? []}
                          />
                        )}
                      </div>
                    </Card>
                  </div>
                </WorkbenchTabPanel>
              ) : null}

              {resolvedActiveTabId === 'network' ? (
                <WorkbenchTabPanel key="network" tabId="network">
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
                          onChange={(event) => {
                            const nextSearch = new URLSearchParams(searchParams)
                            nextSearch.set('depth', event.target.value)
                            setSearchParams(nextSearch)
                          }}
                          value={depth}
                        >
                          {[1, 2, 3, 4, 5].map((value) => (
                            <option key={value} value={value}>{value}</option>
                          ))}
                        </select>
                      </div>
                      {neighborhood ? (
                        <>
                          <div className="investigation-graph-canvas">
                            <GraphCanvas
                              centerEntityId={entity.id}
                              clusterMode={clusterMode}
                              entityTypes={domainConfigQuery.data.entities.map((e) => e.name)}
                              highlightedEntityIds={selectedCluster?.entity_ids}
                              labelFor={labelForNode}
                              onSelectNode={navigateToEntity}
                              selectedEntityId={entity.id}
                              subgraph={toSubgraphResult(neighborhood.entities, neighborhood.relationships)}
                              testId="investigation-graph-canvas"
                            />
                          </div>
                          {capabilities?.gnn && clusters.length > 0 ? (
                            <ClusterMembershipPanel
                              clusters={clusters}
                              onSelectCluster={setSelectedClusterId}
                              selectedClusterId={selectedClusterId}
                            />
                          ) : null}
                        </>
                      ) : (
                        <EmptyState description="Select an entity to load its graph neighborhood." title="No neighborhood loaded" />
                      )}
                    </div>
                  </Card>
                </WorkbenchTabPanel>
              ) : null}

              {resolvedActiveTabId === 'policy' ? (
                <WorkbenchTabPanel key="policy" tabId="policy">
                  <Card>
                    <EntityPolicyPanel
                      knowledgeBaseId={activeKnowledgeBaseId}
                      targetKind="entity"
                      targetRef={selectedEntityId}
                    />
                  </Card>
                </WorkbenchTabPanel>
              ) : null}

              {resolvedActiveTabId === 'evidence' ? (
                <WorkbenchTabPanel key="evidence" tabId="evidence">
                  {evidenceQuery.data && !requestedEvidenceInvalid ? (
                    <EvidencePackViewer
                      // Export only: there is no alert in hand here, and
                      // offering to attach one would mean inventing it.
                      actions={
                        activeKnowledgeBaseId ? (
                          <EvidencePackActions
                            evidencePackId={evidenceQuery.data.id}
                            knowledgeBaseId={activeKnowledgeBaseId}
                          />
                        ) : null
                      }
                      entityTypes={domainConfigQuery.data.entities.map((e) => e.name)}
                      labelFor={labelForNode}
                      onSelectNode={navigateToEntity}
                      pack={evidenceQuery.data}
                      selectedEntityId={selectedEntityId}
                      subgraph={
                        neighborhood
                          ? toSubgraphResult(neighborhood.entities, neighborhood.relationships)
                          : { nodes: [], edges: [] }
                      }
                    />
                  ) : (
                    <Card>
                      <EmptyState
                        action={
                          <Link className="page-button" to="/alerts">
                            Open Alert Feed
                          </Link>
                        }
                        description="No evidence pack is linked to this entity yet. Review the alert feed for open investigations."
                        title="No evidence available"
                      />
                    </Card>
                  )}
                </WorkbenchTabPanel>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </section>
  )
}

function depthFromSearchParams(searchParams: URLSearchParams): number {
  const value = Number(searchParams.get('depth') ?? 2)
  if (!Number.isInteger(value)) {
    return 2
  }
  return Math.min(Math.max(value, 1), 5)
}

type AnalyticsAvailability = {
  availability_status?: 'available' | 'unavailable'
  unavailable_reason?: string | null
}

type AnalyticsAvailabilityState = {
  unavailable: boolean
  reason: string | null
}

function analyticsAvailability(payload: unknown): AnalyticsAvailabilityState {
  if (!payload || typeof payload !== 'object') {
    return { unavailable: false, reason: null }
  }
  const availability = payload as AnalyticsAvailability
  const unavailable = availability.availability_status === 'unavailable'
  return {
    unavailable,
    reason: unavailable ? availability.unavailable_reason ?? null : null,
  }
}
