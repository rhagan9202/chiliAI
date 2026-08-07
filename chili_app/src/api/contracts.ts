import type { components } from '../lib/api/schema'

type Schemas = components['schemas']
type RequireFields<T, K extends keyof T> = T & {
  [P in K]-?: NonNullable<T[P]>
}
type OptionalFields<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>

export type PageInfo = Schemas['PageInfo']

export type AlertSeverity = Schemas['AlertListItem']['severity']
export type AlertStatus = Schemas['AlertListItem']['status']
export type AlertListItem = RequireFields<Schemas['AlertListItem'], 'tags'>
export type AlertListResponse = RequireFields<Schemas['AlertListResponse'], 'items'>
export type AlertDetailResponse = RequireFields<
  Schemas['AlertDetailResponse'],
  'policy_citations' | 'related_entity_ids'
>
export type AlertOperationResponse = Schemas['AlertOperationResponse']
export type AlertBulkStatusUpdateResponse = RequireFields<
  Schemas['AlertBulkStatusUpdateResponse'],
  'rejected_alerts' | 'updated_alerts'
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
export type IdentityLinkDecisionRecordResponse = Schemas['IdentityLinkDecisionRecordResponse']
export type IdentityLinkResponse = RequireFields<
  Schemas['IdentityLinkResponse'],
  'decision_history' | 'match_reasons' | 'source_refs'
>
export type CanonicalIdentityDetailResponse = Omit<
  Schemas['CanonicalIdentityDetailResponse'],
  'links'
> & {
  links: IdentityLinkResponse[]
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
export type PlaybookRef = Schemas['PlaybookRef']
export type PlaybookEvidenceRequirementResponse = Schemas['PlaybookEvidenceRequirementResponse']
export type PlaybookWorkflowStepResponse = Schemas['PlaybookWorkflowStepResponse']
export type PlaybookRagPromptResponse = Schemas['PlaybookRagPromptResponse']
export type PlaybookResponse = RequireFields<
  Schemas['PlaybookResponse'],
  'decision_guidance' | 'evidence_requirements' | 'rag_prompts' | 'workflow_steps'
>
export type PlaybookSnapshotResponse = Omit<Schemas['PlaybookSnapshotResponse'], 'definition'> & {
  definition: PlaybookResponse
}
export type PlaybookListResponse = Omit<
  RequireFields<Schemas['PlaybookListResponse'], 'items' | 'published'>,
  'items' | 'published'
> & {
  items: PlaybookResponse[]
  published: PlaybookSnapshotResponse[]
}
export type PlaybookPublishRequestPayload = Schemas['PlaybookPublishRequestPayload']
export type PlaybookImportRequestPayload = Schemas['PlaybookImportRequestPayload']
export type PlaybookImportResponse = RequireFields<Schemas['PlaybookImportResponse'], 'snapshot_ids'>
export type PlaybookExportResponse = Schemas['PlaybookExportResponse']
export type CapabilityListResponse = RequireFields<Schemas['CapabilityListResponse'], 'items'>
export type CapabilityManifestResponse = Schemas['CapabilityManifestResponse']
export type CapabilitySideEffectClass = Schemas['CapabilityManifestResponse']['side_effect_class']
export type KnowledgeBaseReadinessResponse = RequireFields<
  Schemas['KnowledgeBaseReadinessResponse'],
  'blockers' | 'warnings'
>
export type ReadinessComponentResponse = RequireFields<
  Schemas['ReadinessComponentResponse'],
  'blockers' | 'warnings'
>
export type ReadinessIssueResponse = Schemas['ReadinessIssueResponse']
export type GovernanceVersionSummaryResponse = Schemas['GovernanceVersionSummaryResponse']
export type GovernanceEvalRunResponse = RequireFields<
  Schemas['GovernanceEvalRunResponse'],
  'affected_alert_ids' | 'affected_case_ids'
>
export type GovernancePendingApprovalResponse = Schemas['GovernancePendingApprovalResponse']
export type GovernanceFeedbackTrendResponse = RequireFields<
  Schemas['GovernanceFeedbackTrendResponse'],
  'state_counts'
>
export type GovernanceReleaseBlockerResponse = Schemas['GovernanceReleaseBlockerResponse']
export type GovernanceReportResponse = Omit<
  RequireFields<
    Schemas['GovernanceReportResponse'],
    'eval_runs' | 'production_versions' | 'pending_approvals' | 'release_blockers'
  >,
  'eval_runs' | 'feedback_trends'
> & {
  eval_runs: GovernanceEvalRunResponse[]
  feedback_trends: GovernanceFeedbackTrendResponse
}
export type CaseSummaryResponse = RequireFields<Schemas['CaseSummaryResponse'], 'alert_ids'>
export type CaseListResponse = RequireFields<Schemas['CaseListResponse'], 'items'>
export type CaseTimelineEventResponse = Schemas['CaseTimelineEventResponse']
export type AuditEventResponse = Schemas['AuditEventResponse']
export type AnalystFeedbackResponse = RequireFields<
  Schemas['AnalystFeedbackResponse'],
  'missing_evidence'
>
export type CaseDetailResponse = RequireFields<
  Schemas['CaseDetailResponse'],
  'alerts' | 'entity_timeline' | 'feedback_history'
>
export type CaseDossierResponse = RequireFields<
  Schemas['CaseDossierResponse'],
  | 'alerts'
  | 'audit_events'
  | 'evidence_packs'
  | 'entity_timeline'
  | 'explanation_review_summaries'
  | 'feedback_history'
>
export type CaseDossierExportResponse = Schemas['CaseDossierExportResponse']
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

export type CaseAttachAlertRequest = Schemas['CaseAttachAlertRequest']
export type EvidenceExportFormat = Schemas['EvidencePackExportResponse']['format']
export type EvidencePackExportResponse = Schemas['EvidencePackExportResponse']
export type ExplanationReviewCreateRequest = Schemas['ExplanationReviewCreateRequest']
export type ExplanationReviewResponse = Schemas['ExplanationReviewResponse']
export type ExplanationReviewListResponse = RequireFields<
  Schemas['ExplanationReviewListResponse'],
  'items'
>

export type RecordPushRequest = Schemas['RecordPushRequest']
export type RecordIngestReceipt = Schemas['RecordIngestReceipt']

export type WorkflowRunResponse = Schemas['WorkflowRunResponse']
export type WorkflowStepApprovalRequest = Schemas['WorkflowStepApprovalRequest']
export type WorkflowStepRejectionRequest = Schemas['WorkflowStepRejectionRequest']
export type WorkflowRunListResponse = RequireFields<Schemas['WorkflowRunListResponse'], 'items'>

export type ScoreBatchResponse = RequireFields<Schemas['ScoreBatchResponse'], 'entity_ids'>
export type ScoreRunStatus = Schemas['ScoreRunResponse']['status']
export type ScoreRunStartRequest = Schemas['ScoreRunStartRequest']
export type ScoreRunReplayRequest = Schemas['ScoreRunReplayRequest']
export type ScoreRunResponse = Schemas['ScoreRunResponse']
export type ScoreRunListResponse = RequireFields<Schemas['ScoreRunListResponse'], 'items'>
export type ScoreRunDetailResponse = Omit<
  RequireFields<Schemas['ScoreRunDetailResponse'], 'batches'>,
  'batches'
> & {
  batches: ScoreBatchResponse[]
}

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
export type RiskProjectionItemResponse = Schemas['RiskProjectionItemResponse']
export type RiskProjectionListResponse = RequireFields<
  Schemas['RiskProjectionListResponse'],
  'items'
>
export type RiskScoreResponse = RequireFields<Schemas['RiskScoreResponse'], 'factors'>
export type RiskScoreListResponse = Schemas['RiskScoreListResponse']
export type TimeseriesPointResponse = Schemas['EntityTimeseriesPointResponse']
export type TimeseriesResponse = RequireFields<Schemas['EntityTimeseriesResponse'], 'points'>
export type MetricTimeseriesResponse = Schemas['MetricTimeseriesResponse']
export type ClusterResult = Schemas['ClusterResult']
export type GnnClusterResponse = Schemas['GnnClusterResponse']
export type AnalyticsOverviewResponse = Schemas['AnalyticsOverviewResponse']
export type PeerDistributionSummaryResponse = Schemas['PeerDistributionSummaryResponse']
export type PeerCohortContextResponse = Schemas['PeerCohortContextResponse']
export type PeerMetricComparisonResponse = Schemas['PeerMetricComparisonResponse']
export type PeerAnalysisResponse = RequireFields<Schemas['PeerAnalysisResponse'], 'metrics'>
export type FeatureSourceMappingResponse = RequireFields<
  Schemas['FeatureSourceMappingResponse'],
  'raw_fields'
>
export type FeatureDefinitionResponse = Omit<
  RequireFields<
    Schemas['FeatureDefinitionResponse'],
    'entity_types' | 'peer_dimensions' | 'source_mappings' | 'typology_ids'
  >,
  'source_mappings'
> & {
  source_mappings: FeatureSourceMappingResponse[]
}
export type FraudTypologyResponse = RequireFields<
  Schemas['FraudTypologyResponse'],
  'entity_types' | 'feature_ids' | 'playbook_ids' | 'policy_rule_ids'
>
export type FeatureCatalogResponse = Omit<
  RequireFields<Schemas['FeatureCatalogResponse'], 'features' | 'typologies'>,
  'features' | 'typologies'
> & {
  features: FeatureDefinitionResponse[]
  typologies: FraudTypologyResponse[]
}
export type EntityFeatureValueResponse = RequireFields<
  Schemas['EntityFeatureValueResponse'],
  'source_refs'
>
export type EntityFeatureValueListResponse = Omit<
  RequireFields<Schemas['EntityFeatureValueListResponse'], 'items'>,
  'items'
> & {
  items: EntityFeatureValueResponse[]
}
