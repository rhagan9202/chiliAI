import { knowledgeBaseWorkspacePath } from '../utils/knowledgeBaseRoutes'

import type { RagLaunchContext } from './ragContext'

export type EvidenceCitationReference = {
  reference_type: string
  reference_id: string
  label: string
  route_target?: string | null
  metadata?: Record<string, unknown | null>
}

export type RagCitationReference = {
  record_id?: string | null
  content_id?: string | null
  document_id?: string | null
  chunk_index?: number | null
  entity_id?: string | null
}

export type CitationLinkTarget = {
  kind: 'link'
  label: string
  sourceType: string
  to: string
  preview: string
}

export type UnsupportedCitationTarget = {
  kind: 'unsupported'
  label: string
  sourceType: string
  reason: string
}

export type CitationTarget = CitationLinkTarget | UnsupportedCitationTarget

type EvidenceCitationTargetInput = {
  knowledgeBaseId: string | null | undefined
  reference: EvidenceCitationReference
}

type RagCitationTargetInput = {
  citation: RagCitationReference
  context: RagLaunchContext
}

const DERIVED_REFERENCE_TYPES = new Set(['model_version', 'prompt_version'])

const referenceLabel = (reference: EvidenceCitationReference) =>
  reference.label || reference.reference_id || reference.reference_type

const unsupported = (
  label: string,
  sourceType: string,
  reason: string,
): UnsupportedCitationTarget => ({
  kind: 'unsupported',
  label,
  sourceType,
  reason,
})

const appRouteTarget = (routeTarget: string | null | undefined): string | null => {
  if (routeTarget == null || routeTarget.length === 0) return null
  if (!routeTarget.startsWith('/') || routeTarget.startsWith('//') || routeTarget.includes('://')) {
    return null
  }
  try {
    const pathname = routeTarget.split(/[?#]/, 1)[0]
    if (decodeURIComponent(pathname).split('/').some((segment) => segment === '..')) {
      return null
    }
  } catch {
    return null
  }
  return routeTarget
}

const query = (values: Array<[string, string | number | null | undefined]>) => {
  const params = new URLSearchParams()
  values.forEach(([key, value]) => {
    if (value !== null && value !== undefined && String(value).length > 0) {
      params.set(key, String(value))
    }
  })
  const rendered = params.toString()
  return rendered ? `?${rendered}` : ''
}

const routeKb = (routeTarget: string): string | null => {
  const direct = routeTarget.match(/^\/knowledgebases\/([^/?#]+)/)
  if (direct) return decodeURIComponent(direct[1])

  const paramsIndex = routeTarget.indexOf('?')
  if (paramsIndex === -1) return null
  const params = new URLSearchParams(routeTarget.slice(paramsIndex + 1))
  return params.get('kb') ?? params.get('knowledge_base_id')
}

const entityIdFromReference = (reference: EvidenceCitationReference, routeTarget: string | null) => {
  const fromBackendRoute = routeTarget?.match(/^\/investigation\/entities\/([^/?#]+)/)
  if (fromBackendRoute) return decodeURIComponent(fromBackendRoute[1])

  const fromRoute = routeTarget?.match(/^\/investigation\/([^/?#]+)/)
  if (fromRoute) return decodeURIComponent(fromRoute[1])

  const metadataEntityId = reference.metadata?.entity_id
  if (typeof metadataEntityId === 'string' && metadataEntityId.length > 0) {
    return metadataEntityId
  }

  return reference.reference_id || null
}

const documentIdFromReference = (reference: EvidenceCitationReference, routeTarget: string | null) => {
  const fromRoute = routeTarget?.match(/^\/knowledgebases\/[^/?#]+\/documents\/([^/?#]+)\/preview/)
  if (fromRoute) return decodeURIComponent(fromRoute[1])

  const metadataDocumentId = reference.metadata?.document_id
  if (typeof metadataDocumentId === 'string' && metadataDocumentId.length > 0) {
    return metadataDocumentId
  }

  return reference.reference_id.split('#')[0] || null
}

const isRouteMismatch = (knowledgeBaseId: string, routeTarget: string | null) => {
  const targetKb = routeTarget ? routeKb(routeTarget) : null
  return targetKb !== null && targetKb !== knowledgeBaseId
}

export function resolveEvidenceCitationTarget({
  knowledgeBaseId,
  reference,
}: EvidenceCitationTargetInput): CitationTarget {
  const label = referenceLabel(reference)
  const sourceType = reference.reference_type
  const routeTarget = appRouteTarget(reference.route_target)

  if (reference.route_target && routeTarget === null) {
    return unsupported(label, sourceType, 'Citation route target is not a supported app route.')
  }

  if (DERIVED_REFERENCE_TYPES.has(sourceType)) {
    return unsupported(
      label,
      sourceType,
      'Derived model and prompt references do not have a source drill-through yet.',
    )
  }

  if (!knowledgeBaseId) {
    return unsupported(label, sourceType, 'Citation target requires an active knowledge base.')
  }

  if (isRouteMismatch(knowledgeBaseId, routeTarget)) {
    return unsupported(label, sourceType, 'Citation target is outside the active knowledge base.')
  }

  if (sourceType === 'document') {
    const documentId = documentIdFromReference(reference, routeTarget)
    if (!documentId) {
      return unsupported(label, sourceType, 'Document citation is missing a document id.')
    }
    return {
      kind: 'link',
      label,
      sourceType,
      to: `${knowledgeBaseWorkspacePath(knowledgeBaseId, 'data')}${query([
        ['document', documentId],
      ])}`,
      preview: 'Document preview',
    }
  }

  if (
    sourceType === 'graph_node' ||
    sourceType === 'entity' ||
    sourceType === 'risk_factor' ||
    sourceType === 'risk_summary'
  ) {
    const entityId = entityIdFromReference(reference, routeTarget)
    if (!entityId) {
      return unsupported(label, sourceType, 'Graph citation is missing an entity id.')
    }
    return {
      kind: 'link',
      label,
      sourceType,
      to: `/investigation/${encodeURIComponent(entityId)}${query([['kb', knowledgeBaseId]])}`,
      preview: 'Investigation cockpit',
    }
  }

  if (sourceType === 'policy_item') {
    return unsupported(label, sourceType, 'Policy item selection is not routable yet.')
  }

  if (sourceType === 'workflow_run' || sourceType === 'workflow') {
    return unsupported(label, sourceType, 'Workflow run selection is not routable yet.')
  }

  if (sourceType === 'correlation') {
    return unsupported(label, sourceType, 'Correlation references do not have a source drill-through yet.')
  }

  return unsupported(label, sourceType, 'Citation source type does not have a drill-through route yet.')
}

export function resolveRagCitationTarget({
  citation,
  context,
}: RagCitationTargetInput): CitationTarget {
  const knowledgeBaseId = context.knowledgeBaseId

  if (citation.entity_id) {
    if (!knowledgeBaseId) {
      return unsupported(citation.entity_id, 'entity', 'Citation target requires an active knowledge base.')
    }
    return {
      kind: 'link',
      label: citation.entity_id,
      sourceType: 'entity',
      to: `/investigation/${encodeURIComponent(citation.entity_id)}${query([
        ['kb', knowledgeBaseId],
        ['alert', context.alertId],
        ['case', context.caseId],
        ['evidence', context.evidencePackId],
      ])}`,
      preview: 'Investigation cockpit',
    }
  }

  if (citation.document_id) {
    if (!knowledgeBaseId) {
      return unsupported(citation.document_id, 'document', 'Citation target requires an active knowledge base.')
    }
    return {
      kind: 'link',
      label: citation.document_id,
      sourceType: 'document',
      to: `${knowledgeBaseWorkspacePath(knowledgeBaseId, 'data')}${query([
        ['document', citation.document_id],
        ['chunk', citation.chunk_index],
      ])}`,
      preview: 'Document preview',
    }
  }

  return unsupported(
    citation.record_id ?? citation.content_id ?? 'citation',
    'citation',
    'Citation source type does not have a drill-through route yet.',
  )
}
