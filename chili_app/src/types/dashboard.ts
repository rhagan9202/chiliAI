// Dashboard view-model types.

export interface DashboardMetrics {
  totalEntities: number
  totalRelationships: number
  openAlerts: number
  activeKnowledgeBases: number
}

export type ActivityKind =
  | 'kb_created'
  | 'kb_updated'
  | 'document_uploaded'
  | 'alert_opened'
  | 'analysis_completed'

export interface ActivityEvent {
  id: string
  kind: ActivityKind
  description: string
  timestamp: string
  entityId?: string | null
  entityType?: string | null
}
