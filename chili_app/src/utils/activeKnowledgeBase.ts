import type { KnowledgeBaseSummaryResponse } from '../api/contracts'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'

export interface ResolveActiveKnowledgeBaseInput {
  knowledgeBases: readonly KnowledgeBaseSummaryResponse[]
  activeDomainName: string | null
  requestedId: string | null
  storedId: string | null
  /**
   * A knowledge base named by the route path. On a workspace route the URL is
   * the page, so this outranks everything else and is validated against the
   * full list rather than the in-domain one: domain scoping is warn-only, and
   * a cross-domain workspace must render the corpus its address names.
   */
  pathId?: string | null
}

/** Recency key: a KB's last update, falling back to its creation time. */
function recencyOf(knowledgeBase: KnowledgeBaseSummaryResponse): number {
  return Date.parse(knowledgeBase.updated_at ?? knowledgeBase.created_at)
}

export function resolveActiveKnowledgeBaseId(
  input: ResolveActiveKnowledgeBaseInput,
): string | null {
  const pathId = input.pathId ?? null
  if (pathId !== null && input.knowledgeBases.some((item) => item.id === pathId)) {
    return pathId
  }

  const inDomain = input.knowledgeBases.filter(
    (knowledgeBase) =>
      !isDomainMismatch(knowledgeBase.domain ?? null, input.activeDomainName),
  )
  const isSelectable = (candidate: string | null): candidate is string =>
    candidate !== null && inDomain.some((item) => item.id === candidate)

  // An explicit URL selection wins, then the user's remembered choice; both are
  // validated against the in-domain list so a deleted or cross-domain id can
  // never strand a page on a knowledge base the API will refuse.
  if (isSelectable(input.requestedId)) return input.requestedId
  if (isSelectable(input.storedId)) return input.storedId

  // Default to a knowledge base that can actually answer: a still-building KB
  // has no entities or analytics yet, so it only wins when nothing is ready.
  const byRecency = [...inDomain].sort(
    (left, right) => recencyOf(right) - recencyOf(left),
  )
  const mostRecent =
    byRecency.find((knowledgeBase) => knowledgeBase.status === 'ready') ?? byRecency[0]
  return mostRecent?.id ?? null
}
