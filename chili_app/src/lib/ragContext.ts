import { resolveRagCitationTarget, type RagCitationReference } from './citationTargets'

export type RagLaunchSource = 'alert' | 'entity' | 'case' | 'housing'

export type RagLaunchContext = {
  knowledgeBaseId: string | null
  source: RagLaunchSource | null
  alertId?: string | null
  entityId?: string | null
  caseId?: string | null
  evidencePackId?: string | null
  installationId?: string | null
  scorecardRunId?: string | null
  question?: string | null
}

export type RagScope = {
  knowledgeBaseId: string | null
  source: RagLaunchSource | null
  label: string
  filters: Record<string, string | number | boolean>
}

type NavigationTarget = {
  pathname: string
  search: string
}

export const DEFAULT_RISK_QUESTION = 'Why is this high risk?'

const SOURCE_VALUES = new Set<RagLaunchSource>(['alert', 'entity', 'case', 'housing'])

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
  appendIfPresent(params, 'installation', context.installationId)
  appendIfPresent(params, 'scorecardRun', context.scorecardRunId)
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
    installationId: params.get('installation') || null,
    scorecardRunId: params.get('scorecardRun') || null,
    question: params.get('q') || null,
  }
}

function scopeLabel(context: RagLaunchContext): string {
  if (context.source === 'alert' && nonEmpty(context.alertId)) {
    return `Alert ${context.alertId}`
  }
  if (context.source === 'case' && nonEmpty(context.caseId)) {
    return `Case ${context.caseId}`
  }
  if (context.source === 'entity' && nonEmpty(context.entityId)) {
    return `Entity ${context.entityId}`
  }
  if (context.source === 'housing' && nonEmpty(context.installationId)) {
    return `Installation ${context.installationId}`
  }
  if (context.source != null) {
    return context.source
  }
  return 'Knowledge base'
}

export function buildRagScope(context: RagLaunchContext): RagScope {
  return {
    knowledgeBaseId: context.knowledgeBaseId ?? null,
    source: context.source ?? null,
    label: scopeLabel(context),
    filters: Object.fromEntries(
      [
        ['source_type', context.source],
        ['alert_id', context.alertId],
        ['entity_id', context.entityId],
        ['case_id', context.caseId],
        ['evidence_pack_id', context.evidencePackId],
        ['installation_id', context.installationId],
        ['scorecard_run_id', context.scorecardRunId],
      ].filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0),
    ),
  }
}

export function buildRagMessageFilters(context: RagLaunchContext): Record<string, string | number | boolean> {
  return buildRagScope(context).filters
}

export function citationNavigationTarget(
  citation: RagCitationReference,
  context: RagLaunchContext,
): NavigationTarget | null {
  const target = resolveRagCitationTarget({ citation, context })
  if (target.kind !== 'link') return null

  const [pathname, search = ''] = target.to.split('?', 2)
  return { pathname, search }
}
