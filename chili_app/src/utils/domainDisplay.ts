import type { DomainConfig, RuntimeEntity } from '../api/contracts'

export function getEntityTypeLabel(entityType: string, config: DomainConfig) {
  return config.entities.find((entity) => entity.name === entityType)?.display_label ?? entityType
}

export function getRelationshipTypeLabel(relationshipType: string, config: DomainConfig) {
  return config.relationships.find((relationship) => relationship.name === relationshipType)?.display_label ?? relationshipType
}

/**
 * The one name an entity answers to, everywhere.
 *
 * Mirrors `backend/config/display.py::entity_display_label`: the configured
 * title property, then a `name` property, then the entity type's label plus
 * its id. The last rung is deliberately not a bare id — an id alone reads as
 * an internal handle, which is what UXA-304 was filed about. Change both
 * implementations together.
 */
export function getEntityTitle(entity: RuntimeEntity, config: DomainConfig) {
  const fieldName = config.ui?.display_fields?.[entity.type]?.title
  return (
    propertyText(entity, fieldName) ??
    propertyText(entity, 'name') ??
    `${getEntityTypeLabel(entity.type, config)} ${entity.id}`
  )
}

export function getEntitySubtitle(entity: RuntimeEntity, config: DomainConfig) {
  const fieldName = config.ui?.display_fields?.[entity.type]?.subtitle
  return propertyText(entity, fieldName)
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
