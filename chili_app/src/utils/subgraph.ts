import type { RuntimeEntity, RuntimeRelationship } from '../api/contracts'
import type { Entity as ApiEntity, Relationship as ApiRelationship, SubgraphResult } from '../types/api'

// Adapter: collapse RuntimeEntity/RuntimeRelationship (from the investigation
// API contract) into the GraphCanvas SubgraphResult shape. The two surface
// types are structurally compatible (same id/type/properties/metadata/version
// fields), but TypeScript still requires an explicit conversion across the
// nominal interface boundary. Shared by InvestigationWorkbenchPage and
// AlertFeedPage so there is one implementation of the conversion.
export function toSubgraphResult(
  entities: RuntimeEntity[],
  relationships: RuntimeRelationship[],
): SubgraphResult {
  return {
    nodes: entities.map((e): ApiEntity => ({
      id: e.id,
      type: e.type,
      properties: e.properties,
      metadata: e.metadata,
      created_at: e.created_at,
      updated_at: e.updated_at,
      version: e.version,
    })),
    edges: relationships.map((r): ApiRelationship => ({
      id: r.id,
      type: r.type,
      source_id: r.source_id,
      target_id: r.target_id,
      properties: r.properties,
      metadata: r.metadata,
      created_at: r.created_at,
      updated_at: r.updated_at,
      version: r.version,
      weight: r.weight,
    })),
  }
}
