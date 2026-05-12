import type { DomainConfig, RuntimeEntity } from '../api/contracts'

export function getEntityTypeLabel(entityType: string, config: DomainConfig) {
  return config.entities.find((entity) => entity.name === entityType)?.display_label ?? entityType
}

export function getRelationshipTypeLabel(relationshipType: string, config: DomainConfig) {
  return config.relationships.find((relationship) => relationship.name === relationshipType)?.display_label ?? relationshipType
}

export function getEntityTitle(entity: RuntimeEntity, config: DomainConfig) {
  const fieldName = config.ui?.display_fields?.[entity.type]?.title
  return propertyText(entity, fieldName) ?? propertyText(entity, 'name') ?? entity.id
}

export function getEntitySubtitle(entity: RuntimeEntity, config: DomainConfig) {
  const fieldName = config.ui?.display_fields?.[entity.type]?.subtitle
  return propertyText(entity, fieldName)
}

export function getEntityChips(entity: RuntimeEntity, config: DomainConfig) {
  const configuredFields = config.ui?.display_fields?.[entity.type]?.chips ?? []
  const fields = configuredFields.length > 0 ? configuredFields : Object.keys(entity.properties).slice(0, 4)
  return fields.flatMap((fieldName) => {
    const value = propertyText(entity, fieldName)
    return value ? [`${fieldName}: ${value}`] : []
  })
}

export function propertyText(entity: RuntimeEntity, fieldName: string | undefined) {
  if (!fieldName) {
    return null
  }
  const value = entity.properties[fieldName]
  if (value === undefined || value === null) {
    return null
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(', ')
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}
