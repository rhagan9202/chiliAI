// Shared API response shapes consumed by the frontend.
// Mirror the FastAPI router contracts under `backend/api/routers/`.

export type KnowledgeBaseStatus =
  | 'active'
  | 'building'
  | 'ready'
  | 'error'
  | 'archived'

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  entity_count: number
  relationship_count: number
  document_count: number
  status: KnowledgeBaseStatus
  created_at: string
  updated_at?: string | null
}

export interface KnowledgeBaseListResponse {
  items: KnowledgeBase[]
  total: number
}

export interface DocumentSummary {
  id: string
  filename: string
  content_type?: string | null
  size_bytes?: number | null
  status: string
  created_at: string
}

export interface DocumentListResponse {
  items: DocumentSummary[]
  total: number
}

// Alert types have been consolidated in src/api/contracts.ts (AlertListItem,
// AlertSeverity, AlertStatus, AlertListResponse). Import from there.

export interface CreateKnowledgeBaseRequest {
  name: string
  description: string
}

// ---------------------------------------------------------------------------
// Investigation / graph entity types — mirror backend `shared/types.py`
// (`Entity`, `Relationship`, `EvidencePack`) and `graph/service_models.py`
// (`EntityDetailResponse`, `NeighborhoodResponse`, `EntitySearchResponse`).
// ---------------------------------------------------------------------------

export type EntityProperties = Record<string, unknown>

export interface Entity {
  id: string
  type: string
  properties: EntityProperties
  metadata?: EntityProperties
  created_at: string
  updated_at?: string | null
  version: number
}

export interface Relationship {
  id: string
  type: string
  source_id: string
  target_id: string
  properties: EntityProperties
  metadata?: EntityProperties
  created_at: string
  updated_at?: string | null
  version: number
  weight?: number | null
}

export interface SubgraphResult {
  nodes: Entity[]
  edges: Relationship[]
}

export interface EntityDetailResponse {
  entity: Entity
}

export interface NeighborhoodResponse {
  center_entity_id: string
  entities: Entity[]
  relationships: Relationship[]
}

export interface EntitySearchResponse {
  items: Entity[]
  total: number
}

export interface EvidencePack {
  id: string
  alert_id: string
  reasoning: string
  subgraph_nodes: string[]
  subgraph_edges: string[]
  confidence: number
  created_at: string
  scores: Record<string, number>
  source_documents: string[]
}

export interface EvidenceListResponse {
  items: EvidencePack[]
  total: number
}

export interface TimelineEvent {
  id: string
  timestamp: string
  kind: string
  description: string
  entity_id?: string | null
  source?: string | null
}
