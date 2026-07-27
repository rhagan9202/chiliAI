import type { components } from '../lib/api/schema'

type Schemas = components['schemas']
type RequireFields<T, K extends keyof T> = T & {
  [P in K]-?: NonNullable<T[P]>
}
type OptionalFields<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>

export type ApiEnvelope = Schemas['ApiEnvelope']
export type PageInfo = Schemas['PageInfo']

export type AlertSeverity = Schemas['AlertListItem']['severity']
export type AlertStatus = Schemas['AlertListItem']['status']
export type AlertListItem = RequireFields<Schemas['AlertListItem'], 'tags'>
export type AlertListResponse = RequireFields<Schemas['AlertListResponse'], 'items'>
export type AlertDetailResponse = RequireFields<
  Schemas['AlertDetailResponse'],
  'policy_citations' | 'related_entity_ids'
>

export type PolicyCitation = Schemas['PolicyCitation']
export type PolicyItemStatus = Schemas['PolicyItemSummaryResponse']['status']
export type PolicySeverity = Schemas['PolicyItemSummaryResponse']['severity']
export type PolicyItemSummaryResponse = Schemas['PolicyItemSummaryResponse']
export type PolicyItemListResponse = RequireFields<Schemas['PolicyItemListResponse'], 'items'>
export type PolicyItemDetailResponse = RequireFields<
  Schemas['PolicyItemDetailResponse'],
  'matched_fields' | 'citations'
>
export type PolicyTriageRequest = Schemas['PolicyTriageRequest']

export type RealtimeSnapshotResponse = {
  sequence: number
  emitted_at: string
  active_alerts: number
  running_workflows: number
  knowledge_base_statuses: Record<string, string>
}

export type GraphNodeResponse = Schemas['GraphNodeResponse']
export type GraphEdgeResponse = Schemas['GraphEdgeResponse']
export type GraphEntityDetailResponse = RequireFields<
  Schemas['GraphEntityDetailResponse'],
  'neighbors' | 'related_alert_ids' | 'relationships'
>

export type RuntimeEntity = RequireFields<
  Schemas['Entity'],
  'created_at' | 'metadata' | 'properties'
>
export type RuntimeRelationship = RequireFields<
  Schemas['Relationship'],
  'created_at' | 'metadata' | 'properties'
>
export type InvestigationEntityDetailResponse = Omit<Schemas['EntityDetailResponse'], 'entity'> & {
  entity: RuntimeEntity
}
export type InvestigationNeighborhoodResponse = Omit<
  Schemas['NeighborhoodResponse'],
  'entities' | 'relationships'
> & {
  entities: RuntimeEntity[]
  relationships: RuntimeRelationship[]
}
export type InvestigationEntitySearchResponse = Omit<Schemas['EntitySearchResponse'], 'items'> & {
  items: RuntimeEntity[]
}

export type EvidenceItemResponse = Schemas['EvidenceItemResponse']
export type FeatureAttributionResponse = Schemas['FeatureAttributionResponse']
export type EvidencePackResponse = RequireFields<
  Schemas['EvidencePackResponse'],
  'items' | 'policy_citations' | 'scores' | 'subgraph_edge_ids' | 'subgraph_node_ids'
>

export type CaseStatus = Schemas['CaseSummaryResponse']['status']
export type CasePriority = Schemas['CaseSummaryResponse']['priority']
export type FeedbackLabel = Schemas['AnalystFeedbackResponse']['label']
export type EvidenceAdequacy = Schemas['AnalystFeedbackResponse']['evidence_adequacy']
export type CaseSummaryResponse = RequireFields<Schemas['CaseSummaryResponse'], 'alert_ids'>
export type CaseListResponse = RequireFields<Schemas['CaseListResponse'], 'items'>
export type CaseTimelineEventResponse = Schemas['CaseTimelineEventResponse']
export type AnalystFeedbackResponse = RequireFields<
  Schemas['AnalystFeedbackResponse'],
  'missing_evidence'
>
export type CaseDetailResponse = RequireFields<
  Schemas['CaseDetailResponse'],
  'alerts' | 'entity_timeline' | 'feedback_history'
>
export type CaseCreateRequest = Schemas['CaseCreateRequest']
export type CaseUpdateRequest = Schemas['CaseUpdateRequest']
export type CaseFeedbackCreateRequest = Schemas['CaseFeedbackCreateRequest']
export type CasePromoteRequest = Schemas['CasePromoteRequest']

export type ChatCitationResponse = Schemas['ChatCitationResponse']
export type ChatMessageResponse = RequireFields<
  Schemas['ChatMessageResponse'],
  'citation_ids' | 'citations'
>
export type EntityLocationResponse = Schemas['EntityLocationResponse']
export type EntityLocationListResponse = RequireFields<
  Schemas['EntityLocationListResponse'],
  'items'
>
export type ChatConversationSummaryResponse = Schemas['ChatConversationSummaryResponse']
export type ChatConversationListResponse = RequireFields<
  Schemas['ChatConversationListResponse'],
  'items'
>
export type ChatConversationResponse = RequireFields<
  Schemas['ChatConversationResponse'],
  'messages'
>
export type ChatConversationCreateRequest = Schemas['ChatConversationCreateRequest']
export type ChatMessageCreateRequest = Schemas['ChatMessageCreateRequest']

export type KnowledgeBaseStatus = Schemas['KnowledgeBase']['status']
export type KnowledgeBaseSummaryResponse = OptionalFields<Schemas['KnowledgeBase'], 'pending_cleanup'>
export type KnowledgeBaseListResponse = Schemas['KbListResponse']
export type KnowledgeBaseDocumentResponse = Schemas['DocumentSummary']
export type KnowledgeBaseDocumentListResponse = Schemas['DocumentListResponse']
export type KnowledgeBaseDocumentPreviewResponse = Schemas['DocumentPreviewResponse']
export type KnowledgeBaseCreateRequest = Schemas['CreateKbRequest']
export type DocumentReceiptResponse = Schemas['DocumentReceipt']
export type DocumentRegistrationResponse = Schemas['DocumentRegistrationResponse']
export type IngestionStatus = Schemas['DocumentSummary']['status']

export type DomainIngestionConfig = OptionalFields<Schemas['IngestionConfig'], 'sources'>
export type DomainConfig = Partial<Omit<
  Schemas['DomainConfig'],
  'capabilities' | 'entities' | 'ingestion' | 'records' | 'relationships' | 'ui'
>> & {
  alerts: Schemas['AlertsConfig']
  capabilities: DomainCapabilities
  domain: Schemas['DomainInfo']
  entities: DomainEntityDefinition[]
  ingestion: DomainIngestionConfig
  records?: RecordsConfig | null
  relationships: DomainRelationshipDefinition[]
  ui?: DomainUiConfig | null
}
export type DomainFeatures = RequireFields<
  Omit<Schemas['DomainFeaturesResponse'], 'capabilities'>,
  'enabled_pages' | 'roles'
> & {
  capabilities: DomainCapabilities
}
export type DomainCapabilities = OptionalFields<
  Schemas['CapabilitiesConfig'],
  'structured_ingestion'
>
export type DomainPropertyDefinition = OptionalFields<
  Schemas['PropertyDefinition'],
  'enum_values' | 'max_length' | 'max_value' | 'min_length' | 'min_value' | 'pattern' | 'required'
>
export type DomainEntityDefinition = OptionalFields<
  Omit<Schemas['EntityDefinition'], 'properties'>,
  'icon'
> & {
  properties: Record<string, DomainPropertyDefinition>
}
export type DomainRelationshipDefinition = Schemas['RelationshipDefinition']
export type DomainRoleConfig = Schemas['UiRoleConfig']
export type DomainUiConfig = OptionalFields<Schemas['UiConfig'], 'default_entity_type' | 'navigation'>
export type DomainNavigationPage = OptionalFields<Schemas['UiNavigationPageConfig'], 'capability'>
export type ValidationConfig = Schemas['ValidationConfig']
export type RecordFeedConfig = Omit<
  OptionalFields<Schemas['RecordFeedConfig'], 'allow_extra_fields' | 'id_template'>,
  'entities' | 'observations' | 'record_schema' | 'relationships'
> & {
  entities: RecordEntityMapping[]
  observations: RecordObservationMapping[]
  record_schema: Record<string, DomainPropertyDefinition>
  relationships: RecordRelationshipMapping[]
}
export type RecordEntityMapping = OptionalFields<Schemas['RecordEntityMapping'], 'property_fields'>
export type RecordRelationshipMapping = Schemas['RecordRelationshipMapping']
export type RecordObservationMapping = Schemas['RecordObservationMapping']
export type RecordsConfig = RequireFields<Omit<Schemas['RecordsConfig'], 'feeds'>, never> & {
  feeds: RecordFeedConfig[]
}
export type DomainConfigSchema = Record<string, unknown>

export type ActivePackState = Schemas['ActivePackState']
export type PackTransport = Schemas['PackTransport']
export type PackSummary = Schemas['PackSummary']
export type PackListResponse = RequireFields<Schemas['PackListResponse'], 'packs'>
export type ValidatePackRequest = Schemas['ValidatePackRequest']
export type ConfigValidationIssue = RequireFields<Schemas['ConfigValidationIssue'], 'loc'>
export type ValidatePackResponse = RequireFields<Schemas['ValidatePackResponse'], 'errors'>
export type ApplyPackRequest = Schemas['ApplyPackRequest']
export type SwitchPackRequest = Schemas['SwitchPackRequest']
export type ConfigSwapResponse = Schemas['ConfigSwapResponse']

export type RecordPushRequest = Schemas['RecordPushRequest']
export type RecordIngestReceipt = Schemas['RecordIngestReceipt']

export type WorkflowRunResponse = Schemas['WorkflowRunResponse']
export type WorkflowRunListResponse = RequireFields<Schemas['WorkflowRunListResponse'], 'items'>

export type ScorecardRunStatus = Schemas['ScorecardRunResponse']['status']
export type ScorecardExportFormat = Schemas['ScorecardExportResponse']['format']
export type ScorecardTemplateResponse = Schemas['ScorecardTemplateResponse']
export type ScorecardTemplateListResponse = RequireFields<
  Schemas['ScorecardTemplateListResponse'],
  'items'
>
export type ScorecardRunGenerateRequest = Schemas['ScorecardRunGenerateRequest']
export type ScorecardCitationResponse = Schemas['ScorecardCitationResponse']
export type ScorecardMetricResponse = RequireFields<
  Schemas['ScorecardMetricResponse'],
  'citations' | 'warnings'
>
export type ScorecardSectionResponse = Omit<Schemas['ScorecardSectionResponse'], 'metrics'> & {
  metrics: ScorecardMetricResponse[]
}
export type ScorecardRunResponse = Omit<
  RequireFields<Schemas['ScorecardRunResponse'], 'sections'>,
  'sections'
> & {
  sections: ScorecardSectionResponse[]
}
export type ScorecardRunListResponse = Omit<
  RequireFields<Schemas['ScorecardRunListResponse'], 'items'>,
  'items'
> & {
  items: ScorecardRunResponse[]
}
export type ScorecardExportResponse = Schemas['ScorecardExportResponse']

export type HousingPortfolioSummaryResponse = Schemas['HousingPortfolioSummaryResponse']
export type HousingExecutiveKpiResponse = Schemas['HousingExecutiveKpiResponse']
export type HousingOverviewResponse = RequireFields<
  Schemas['HousingOverviewResponse'],
  'executive_kpis' | 'portfolio_summary'
>
export type HousingInstallationResponse = Schemas['HousingInstallationResponse']
export type HousingInstallationMapPointResponse = Schemas['HousingInstallationMapPointResponse']
export type HousingInstallationsResponse = RequireFields<
  Schemas['HousingInstallationsResponse'],
  'items' | 'map_points'
>

export type RiskFactorResponse = Schemas['RiskFactorResponse']
export type RiskScoreResponse = RequireFields<Schemas['RiskScoreResponse'], 'factors'>
export type RiskScoreListResponse = Schemas['RiskScoreListResponse']
export type TimeseriesPointResponse = Schemas['EntityTimeseriesPointResponse']
export type TimeseriesResponse = RequireFields<Schemas['EntityTimeseriesResponse'], 'points'>
export type MetricTimeseriesResponse = Schemas['MetricTimeseriesResponse']
export type ClusterResult = Schemas['ClusterResult']
export type GnnClusterResponse = Schemas['GnnClusterResponse']
export type AnalyticsOverviewResponse = Schemas['AnalyticsOverviewResponse']
