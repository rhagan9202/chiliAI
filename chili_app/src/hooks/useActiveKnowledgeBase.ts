import { useCallback, useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import type { KnowledgeBaseSummaryResponse } from '../api/contracts'
import { useKnowledgeBases } from '../api/knowledgebases'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { useAppStore } from '../stores/appStore'
import { resolveActiveKnowledgeBaseId } from '../utils/activeKnowledgeBase'

/** Query-string key carrying an explicit knowledge-base selection. */
export const KNOWLEDGE_BASE_SEARCH_PARAM = 'kb'

export interface UseActiveKnowledgeBaseResult {
  /** The knowledge base every KB-scoped page on screen should read. */
  activeKnowledgeBaseId: string | null
  /** In-domain knowledge bases, for selector UIs. */
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  isLoading: boolean
  isError: boolean
  setActiveKnowledgeBase: (id: string) => void
}

/**
 * The single answer to "which knowledge base am I looking at".
 *
 * Precedence is `?kb=` → the remembered selection → the most recently updated
 * in-domain knowledge base. Every page reads this instead of picking its own,
 * so counts and detail views can no longer disagree with each other (UXA-101).
 */
export function useActiveKnowledgeBase(): UseActiveKnowledgeBaseResult {
  const [searchParams, setSearchParams] = useSearchParams()
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()

  const storedId = useAppStore((state) => state.activeKnowledgeBaseId)
  const rememberKnowledgeBase = useAppStore((state) => state.setActiveKnowledgeBase)

  const allKnowledgeBases = useMemo(
    () => knowledgeBasesQuery.data?.items ?? [],
    [knowledgeBasesQuery.data],
  )
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null
  const requestedId = searchParams.get(KNOWLEDGE_BASE_SEARCH_PARAM)

  const knowledgeBases = useMemo(
    () =>
      allKnowledgeBases.filter(
        (knowledgeBase) =>
          !isDomainMismatch(knowledgeBase.domain ?? null, activeDomainName),
      ),
    [allKnowledgeBases, activeDomainName],
  )

  const activeKnowledgeBaseId = resolveActiveKnowledgeBaseId({
    knowledgeBases: allKnowledgeBases,
    activeDomainName,
    requestedId,
    storedId,
  })

  // Remember whatever we resolved so a sibling page — or the next session —
  // opens on the same knowledge base.
  useEffect(() => {
    if (activeKnowledgeBaseId !== null && activeKnowledgeBaseId !== storedId) {
      rememberKnowledgeBase(activeKnowledgeBaseId)
    }
  }, [activeKnowledgeBaseId, storedId, rememberKnowledgeBase])

  const setActiveKnowledgeBase = useCallback(
    (id: string) => {
      rememberKnowledgeBase(id)
      // Reflect the choice in the URL so the view is shareable, replacing rather
      // than pushing so switching knowledge bases doesn't stack history entries.
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.set(KNOWLEDGE_BASE_SEARCH_PARAM, id)
          return next
        },
        { replace: true },
      )
    },
    [rememberKnowledgeBase, setSearchParams],
  )

  return {
    activeKnowledgeBaseId,
    knowledgeBases,
    isLoading: knowledgeBasesQuery.isLoading,
    isError: knowledgeBasesQuery.isError,
    setActiveKnowledgeBase,
  }
}
