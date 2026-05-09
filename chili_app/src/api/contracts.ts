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
}

export type DomainNavigationPage = {
  id: string
  label: string
  route: string
  capability?: keyof DomainCapabilities | string
}