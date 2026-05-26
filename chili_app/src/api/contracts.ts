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
export type PolicyGapStatus = Schemas['PolicyGapSummaryResponse']['status']
export type PolicyTrendPointResponse = Schemas['PolicyTrendPointResponse']
export type PolicyGapSummaryResponse = Schemas['PolicyGapSummaryResponse']
export type PolicyGapListResponse = RequireFields<Schemas['PolicyGapListResponse'], 'items'>
export type PolicyGapDetailResponse = RequireFields<
  Schemas['PolicyGapDetailResponse'],
  'policy_citations' | 'trend'
>
export type PolicyGapCaseListResponse = RequireFields<
  Schemas['PolicyGapCaseListResponse'],
  'items'
>
export type PolicyBriefCreateRequest = Schemas['PolicyBriefCreateRequest']
export type PolicyBriefResponse = RequireFields<
  Schemas['PolicyBriefResponse'],
  'policy_citations' | 'recommendations'
>

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
export type AnalystFeedbackResponse = RequireFields<
  Schemas['AnalystFeedbackResponse'],
  'missing_evidence'
>
export type CaseDetailResponse = RequireFields<
  Schemas['CaseDetailResponse'],
  'alerts' | 'feedback_history'
>
export type CaseCreateRequest = Schemas['CaseCreateRequest']
export type CaseUpdateRequest = Schemas['CaseUpdateRequest']
export type CaseFeedbackCreateRequest = Schemas['CaseFeedbackCreateRequest']

export type ChatMessageResponse = RequireFields<Schemas['ChatMessageResponse'], 'citation_ids'>
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

export type RecordPushRequest = Schemas['RecordPushRequest']
export type RecordIngestReceipt = Schemas['RecordIngestReceipt']

export type WorkflowRunResponse = Schemas['WorkflowRunResponse']
export type WorkflowRunListResponse = RequireFields<Schemas['WorkflowRunListResponse'], 'items'>

export type RiskFactorResponse = Schemas['RiskFactorResponse']
export type RiskScoreResponse = RequireFields<Schemas['RiskScoreResponse'], 'factors'>
export type TimeseriesPointResponse = Schemas['EntityTimeseriesPointResponse']
export type TimeseriesResponse = RequireFields<Schemas['EntityTimeseriesResponse'], 'points'>
export type AnalyticsOverviewResponse = Schemas['AnalyticsOverviewResponse']
