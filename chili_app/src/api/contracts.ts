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
  enabled_pages: string[]
  roles: Record<string, DomainRoleConfig>
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