// TypeScript mirror of backend `config/schema.py` (DomainConfig).
// Keep in sync with backend/config/schema.py and backend/shared/types.py.

export type PropertyType =
  | 'string'
  | 'integer'
  | 'decimal'
  | 'date'
  | 'list'
  | 'boolean'
  | 'enum'
  | 'nested'

export interface PropertyDefinition {
  type: PropertyType
  display: string
  required?: boolean
  enum_values?: string[] | null
  min_value?: number | null
  max_value?: number | null
  min_length?: number | null
  max_length?: number | null
  pattern?: string | null
}

export interface EntityDefinition {
  name: string
  display_label: string
  icon: string
  properties: Record<string, PropertyDefinition>
}

export interface RelationshipDefinition {
  name: string
  display_label: string
  source: string
  target: string
}

export interface DomainInfo {
  name: string
  display_name: string
  description: string
}

export interface CapabilitiesConfig {
  timeseries: boolean
  gnn: boolean
  risk_scoring: boolean
  rag_chat: boolean
  explainability: boolean
}

export interface IngestionSourceConfig {
  type: 'file_upload' | 'api_push'
  formats?: string[] | null
  format?: string | null
  endpoint?: string | null
}

export interface ChunkingConfig {
  strategy: 'recursive' | 'fixed_size' | 'sentence'
  chunk_size: number
  chunk_overlap: number
  min_chunk_size: number
  record_template?: string | null
}

export interface IngestionConfig {
  sources: IngestionSourceConfig[]
  chunking: ChunkingConfig
}

export interface GraphDbConfig {
  backend: 'neo4j' | 'in_memory'
  uri?: string | null
  pool_size: number
  auth_env_var?: string | null
}

export interface VectorStoreConfig {
  backend: 'qdrant' | 'in_memory'
  uri?: string | null
  dimensions: number
  distance_metric: 'cosine' | 'dot' | 'euclidean'
}

export interface LlmConfig {
  provider: 'openai' | 'anthropic' | 'local'
  model: string
  api_key_env_var?: string | null
  temperature: number
  max_tokens: number
}

export interface EmbeddingsConfig {
  provider: 'openai' | 'sentence_transformers' | 'local'
  model: string
  dimensions: number
  batch_size: number
  api_key_env_var?: string | null
}

export interface ObjectStoreConfig {
  backend: 's3' | 'minio' | 'local'
  endpoint_url?: string | null
  bucket?: string | null
  base_path?: string | null
  credentials_env_var?: string | null
}

export interface EventBusConfig {
  backend: 'redis' | 'in_memory'
  uri?: string | null
  stream_prefix: string
  consumer_group: string
}

export interface MonitoringConfig {
  evaluation_interval_seconds: number
  dedup_window_seconds: number
  max_alerts_per_entity: number
  max_alerts_per_evaluation: number
  grouping_window_seconds: number
}

export interface RagConfig {
  top_k: number
  expansion_depth: number
  reranking_enabled: boolean
  system_prompt_template?: string | null
}

export interface AlertsConfig {
  thresholds: Record<string, Record<string, number>>
}

export interface DomainConfig {
  schema_version: string
  domain: DomainInfo
  entities: EntityDefinition[]
  relationships: RelationshipDefinition[]
  capabilities: CapabilitiesConfig
  ingestion: IngestionConfig
  graph?: GraphDbConfig | null
  vectorstore?: VectorStoreConfig | null
  llm?: LlmConfig | null
  embeddings?: EmbeddingsConfig | null
  storage?: ObjectStoreConfig | null
  events?: EventBusConfig | null
  monitoring?: MonitoringConfig | null
  rag?: RagConfig | null
  alerts: AlertsConfig
}
