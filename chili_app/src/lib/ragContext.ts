export type RagLaunchSource = 'alert' | 'entity' | 'case'

export type RagLaunchContext = {
  knowledgeBaseId: string | null
  source: RagLaunchSource | null
  alertId?: string | null
  entityId?: string | null
  caseId?: string | null
  evidencePackId?: string | null
  question?: string | null
}

type RagCitation = {
  content_id?: string | null
  entity_id?: string | null
}

type NavigationTarget = {
  pathname: string
  search: string
}

export const DEFAULT_RISK_QUESTION = 'Why is this high risk?'

const SOURCE_VALUES = new Set<RagLaunchSource>(['alert', 'entity', 'case'])

const nonEmpty = (value: string | null | undefined): value is string =>
  typeof value === 'string' && value.length > 0

const appendIfPresent = (params: URLSearchParams, key: string, value: string | null | undefined) => {
  if (nonEmpty(value)) {
    params.set(key, value)
  }
}

export function buildRagChatUrl(context: RagLaunchContext): string {
  const params = new URLSearchParams()

  appendIfPresent(params, 'kb', context.knowledgeBaseId)
  appendIfPresent(params, 'source', context.source)
  appendIfPresent(params, 'alert', context.alertId)
  appendIfPresent(params, 'entity', context.entityId)
  appendIfPresent(params, 'case', context.caseId)
  appendIfPresent(params, 'evidence', context.evidencePackId)
  appendIfPresent(params, 'q', context.question)

  const query = params.toString()
  return query ? `/rag-chat?${query}` : '/rag-chat'
}

export function parseRagLaunchContext(params: URLSearchParams): Required<RagLaunchContext> {
  const source = params.get('source')

  return {
    knowledgeBaseId: params.get('kb') || null,
    source: source != null && SOURCE_VALUES.has(source as RagLaunchSource) ? (source as RagLaunchSource) : null,
    alertId: params.get('alert') || null,
    entityId: params.get('entity') || null,
    caseId: params.get('case') || null,
    evidencePackId: params.get('evidence') || null,
    question: params.get('q') || null,
  }
}

export function buildRagMessageFilters(context: RagLaunchContext): Record<string, string | number | boolean> {
  return Object.fromEntries(
    [
      ['source_type', context.source],
      ['alert_id', context.alertId],
      ['entity_id', context.entityId],
      ['case_id', context.caseId],
      ['evidence_pack_id', context.evidencePackId],
    ].filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0),
  )
}

export function citationNavigationTarget(
  citation: RagCitation,
  context: RagLaunchContext,
): NavigationTarget | null {
  if (nonEmpty(citation.entity_id)) {
    const params = new URLSearchParams()
    appendIfPresent(params, 'kb', context.knowledgeBaseId)

    return {
      pathname: `/investigation/${encodeURIComponent(citation.entity_id)}`,
      search: params.toString(),
    }
  }

  if (context.source === 'alert' && nonEmpty(context.alertId)) {
    return {
      pathname: '/alerts',
      search: new URLSearchParams({ alert: context.alertId }).toString(),
    }
  }

  if (context.source === 'case' && nonEmpty(context.caseId)) {
    const params = new URLSearchParams()
    appendIfPresent(params, 'kb', context.knowledgeBaseId)
    params.set('case', context.caseId)

    return {
      pathname: '/cases',
      search: params.toString(),
    }
  }

  return null
}
