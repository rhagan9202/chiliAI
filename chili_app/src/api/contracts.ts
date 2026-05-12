export type DomainPropertyDefinition = {
  type: string
  display: string
  required?: boolean
  pattern?: string
  min_value?: number
  max_value?: number
  enum_values?: string[]
}

export type DomainEntityDefinition = {
  name: string
  display_label: string
  icon?: string
  properties: Record<string, DomainPropertyDefinition>
}

export type DomainRelationshipDefinition = {
  name: string
  display_label: string
  source: string
  target: string
}

export type DomainCapabilities = {
  timeseries: boolean
  gnn: boolean
  risk_scoring: boolean
  rag_chat: boolean
  explainability: boolean
}

export type DomainConfig = {
  domain: {
    name: string
    display_name: string
    description: string
  }
  entities: DomainEntityDefinition[]
  relationships: DomainRelationshipDefinition[]
  capabilities: DomainCapabilities
  ingestion: Record<string, unknown>
  alerts: {
    thresholds: Record<string, Record<string, number>>
  }
  ui?: DomainUiConfig
}

export type DomainRoleConfig = {
  landing_page: string
  pages: string[]
  permissions: string[]
}

export type DomainUiConfig = {
  default_entity_type?: string
  navigation?: {
    pages: DomainNavigationPage[]
  }
  display_fields?: Record<
    string,
    {
      title: string
      subtitle?: string
      chips?: string[]
    }
  >
  roles?: Record<string, DomainRoleConfig>
}

export type DomainNavigationPage = {
  id: string
  label: string
  route: string
  capability?: keyof DomainCapabilities | string
}

export type DomainFeatures = {
  capabilities: DomainCapabilities
  default_entity_type: string | null
  default_role: string | null
  enabled_pages: string[]
  roles: Record<string, DomainRoleConfig>
}

export type RealtimeSnapshotResponse = {
  sequence: number
  emitted_at: string
  active_alerts: number
  running_workflows: number
  knowledge_base_statuses: Record<string, string>
}

export type DomainConfigSchema = {
  title: string
  properties: Record<string, unknown>
  required?: string[]
}

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AlertStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed'
export type CaseStatus = 'open' | 'in_review' | 'closed'
export type CasePriority = 'low' | 'medium' | 'high' | 'critical'
export type FeedbackLabel = 'suspicious' | 'not_suspicious' | 'insufficient_evidence'
export type EvidenceAdequacy = 'low' | 'medium' | 'high'

export type PageInfo = {
  page: number
  page_size: number
  total_items: number
}

export type PolicyCitation = {
  citation_id: string
  title: string
  excerpt: string
  source_document_id: string
}

export type PolicyGapStatus = 'monitoring' | 'drafting' | 'recommended'

export type PolicyTrendPointResponse = {
  label: string
  value: number
}

export type PolicyGapSummaryResponse = {
  id: string
  title: string
  status: PolicyGapStatus
  severity: 'medium' | 'high' | 'critical'
  impacted_entities: number
  affected_case_count: number
  knowledge_base_id: string
  updated_at: string
}

export type PolicyGapListResponse = {
  items: PolicyGapSummaryResponse[]
  page: PageInfo
}

export type PolicyGapDetailResponse = {
  gap: PolicyGapSummaryResponse
  summary: string
  impact_statement: string
  recommendation: string
  policy_citations: PolicyCitation[]
  trend: PolicyTrendPointResponse[]
}

export type PolicyGapCaseListResponse = {
  gap_id: string
  items: CaseSummaryResponse[]
  page: PageInfo
}

export type PolicyBriefCreateRequest = {
  gap_id: string
  audience: string
  objective: string
}

export type PolicyBriefResponse = {
  id: string
  gap_id: string
  title: string
  audience: string
  objective: string
  narrative: string
  recommendations: string[]
  policy_citations: PolicyCitation[]
  created_at: string
}

export type AlertListItem = {
  id: string
  entity_id: string
  entity_type: string
  entity_label: string
  severity: AlertSeverity
  status: AlertStatus
  title: string
  reasoning: string
  confidence: number
  evidence_pack_id: string | null
  created_at: string
  tags: string[]
}

export type AlertListResponse = {
  items: AlertListItem[]
  page: PageInfo
}

export type AlertDetailResponse = {
  alert: AlertListItem
  related_entity_ids: string[]
  policy_citations: PolicyCitation[]
}

export type ApiEnvelope = {
  status: 'accepted' | 'ok'
  message: string
}

export type GraphNodeResponse = {
  id: string
  type: string
  label: string
  summary: string
  risk_score: number
  properties: Record<string, string | number | boolean>
}

export type GraphEdgeResponse = {
  id: string
  type: string
  source_id: string
  target_id: string
  summary: string
}

export type GraphEntityDetailResponse = {
  entity: GraphNodeResponse
  neighbors: GraphNodeResponse[]
  relationships: GraphEdgeResponse[]
  related_alert_ids: string[]
}

export type RuntimeEntity = {
  id: string
  type: string
  properties: Record<string, unknown>
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string | null
  version: number
}

export type RuntimeRelationship = {
  id: string
  type: string
  source_id: string
  target_id: string
  properties: Record<string, unknown>
  created_at: string
  updated_at: string | null
  version: number
  weight: number | null
}

export type InvestigationEntityDetailResponse = {
  entity: RuntimeEntity
}

export type InvestigationNeighborhoodResponse = {
  center_entity_id: string
  entities: RuntimeEntity[]
  relationships: RuntimeRelationship[]
}

export type InvestigationEntitySearchResponse = {
  items: RuntimeEntity[]
  total: number
}

export type EvidenceItemResponse = {
  source_id: string
  source_type: string
  quote: string
  rationale: string
  score: number
}

export type EvidencePackResponse = {
  id: string
  alert_id: string
  reasoning: string
  confidence: number
  scores: Record<string, number>
  subgraph_node_ids: string[]
  subgraph_edge_ids: string[]
  items: EvidenceItemResponse[]
  policy_citations: PolicyCitation[]
}

export type CaseSummaryResponse = {
  id: string
  title: string
  status: CaseStatus
  priority: CasePriority
  assignee: string | null
  alert_ids: string[]
  updated_at: string
}

export type CaseListResponse = {
  items: CaseSummaryResponse[]
  page: PageInfo
}

export type AnalystFeedbackResponse = {
  case_id: string
  label: FeedbackLabel
  evidence_adequacy: EvidenceAdequacy
  missing_evidence: string[]
  notes: string
  submitted_at: string
}

export type CaseDetailResponse = {
  case: CaseSummaryResponse
  alerts: AlertListItem[]
  feedback_history: AnalystFeedbackResponse[]
}

export type CaseCreateRequest = {
  title: string
  priority: CasePriority
  assignee?: string | null
  alert_ids: string[]
}

export type CaseUpdateRequest = {
  title?: string
  status?: CaseStatus
  priority?: CasePriority
  assignee?: string | null
}

export type CaseFeedbackCreateRequest = {
  label: FeedbackLabel
  evidence_adequacy: EvidenceAdequacy
  missing_evidence: string[]
  notes: string
}

export type ChatMessageResponse = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  citation_ids: string[]
}

export type ChatConversationResponse = {
  id: string
  title: string
  knowledge_base_id: string
  messages: ChatMessageResponse[]
}

export type ChatConversationCreateRequest = {
  knowledge_base_id: string
  title?: string
}

export type ChatMessageCreateRequest = {
  content: string
  include_graph_context?: boolean
  filters?: Record<string, string | number | boolean>
}

export type KnowledgeBaseStatus = 'active' | 'building' | 'ready' | 'error' | 'archived'
export type IngestionStatus = 'pending' | 'registered' | 'building' | 'ready' | 'failed' | 'error'

export type KnowledgeBaseSummaryResponse = {
  id: string
  name: string
  description: string
  status: KnowledgeBaseStatus
  document_count: number
  entity_count: number
  relationship_count: number
  created_at: string
}

export type KnowledgeBaseListResponse = {
  items: KnowledgeBaseSummaryResponse[]
  total: number
}

export type KnowledgeBaseDocumentResponse = {
  id: string
  knowledge_base_id: string
  filename: string
  content_type: string | null
  size_bytes: number | null
  status: IngestionStatus
  created_at: string
}

export type KnowledgeBaseDocumentListResponse = {
  items: KnowledgeBaseDocumentResponse[]
  total: number
}

export type KnowledgeBaseCreateRequest = {
  name: string
  description: string
}

export type DocumentReceiptResponse = {
  knowledge_base_id: string
  source_document_id: string
  filename: string | null
  status: IngestionStatus
  storage_key: string | null
  uri: string | null
  document_format: string | null
  created_at: string
}

export type DocumentRegistrationResponse = {
  documents: DocumentReceiptResponse[]
}

export type WorkflowRunResponse = {
  id: string
  workflow_type: 'ingestion' | 'graph_build' | 'analytics' | 'monitoring'
  status: 'queued' | 'running' | 'completed' | 'failed'
  knowledge_base_id: string
  started_at: string
  updated_at: string
  current_step: string
}

export type WorkflowRunListResponse = {
  items: WorkflowRunResponse[]
}

export type RiskFactorResponse = {
  factor_name: string
  contribution: number
  rationale: string | null
}

export type RiskScoreResponse = {
  entity_id: string
  overall_score: number
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  factors: RiskFactorResponse[]
}

export type TimeseriesPointResponse = {
  timestamp: string
  value: number
  label: string
  is_anomaly: boolean
}

export type TimeseriesResponse = {
  entity_id: string
  metric_name: string
  points: TimeseriesPointResponse[]
}

export type AnalyticsOverviewResponse = {
  active_alerts: number
  open_cases: number
  entities_monitored: number
  high_risk_entities: number
}
