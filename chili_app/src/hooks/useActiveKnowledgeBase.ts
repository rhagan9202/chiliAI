import { useCallback, useEffect, useMemo } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import type { KnowledgeBaseSummaryResponse } from '../api/contracts'
import { useKnowledgeBases } from '../api/knowledgebases'
import { isDomainMismatch } from '../components/knowledgebase/domainMismatch'
import { useAppStore } from '../stores/appStore'
import { resolveActiveKnowledgeBaseId } from '../utils/activeKnowledgeBase'
import {
  knowledgeBaseSelectionTarget,
  matchWorkspacePath,
} from '../utils/knowledgeBaseRoutes'

/** Query-string key carrying an explicit knowledge-base selection. */
export const KNOWLEDGE_BASE_SEARCH_PARAM = 'kb'

export interface UseActiveKnowledgeBaseResult {
  /** The knowledge base every KB-scoped page on screen should read. */
  activeKnowledgeBaseId: string | null
  /**
   * In-domain knowledge bases, for selector UIs — plus, when the active
   * knowledge base is a cross-domain workspace named by the route, that one
   * knowledge base too (see below), so the picker can always name what is on
   * screen.
   */
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  isLoading: boolean
  isError: boolean
  setActiveKnowledgeBase: (id: string) => void
}

/**
 * The single answer to "which knowledge base am I looking at".
 *
 * Precedence is the workspace route path → `?kb=` → the remembered selection
 * → the most recently updated in-domain knowledge base. Every page reads this
 * instead of picking its own, so counts and detail views can no longer
 * disagree with each other (UXA-101).
 */
export function useActiveKnowledgeBase(): UseActiveKnowledgeBaseResult {
  const [searchParams, setSearchParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
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
  // A workspace path names its knowledge base. Reading it here is what makes
  // the top bar, the readiness chip and the page body agree (UXA-101).
  const pathId = matchWorkspacePath(location.pathname)?.knowledgeBaseId ?? null

  const activeKnowledgeBaseId = resolveActiveKnowledgeBaseId({
    knowledgeBases: allKnowledgeBases,
    activeDomainName,
    pathId,
    requestedId,
    storedId,
  })

  const inDomainKnowledgeBases = useMemo(
    () =>
      allKnowledgeBases.filter(
        (knowledgeBase) => !isDomainMismatch(knowledgeBase.domain ?? null, activeDomainName),
      ),
    [allKnowledgeBases, activeDomainName],
  )

  // Whatever is active must be selectable, even when domain scoping would hide
  // it: the picker names what is on screen, and a picker that cannot name it
  // shows the wrong knowledge base instead.
  const knowledgeBases = useMemo(() => {
    if (
      activeKnowledgeBaseId === null ||
      inDomainKnowledgeBases.some((item) => item.id === activeKnowledgeBaseId)
    ) {
      return inDomainKnowledgeBases
    }
    const active = allKnowledgeBases.find((item) => item.id === activeKnowledgeBaseId)
    return active ? [...inDomainKnowledgeBases, active] : inDomainKnowledgeBases
  }, [allKnowledgeBases, inDomainKnowledgeBases, activeKnowledgeBaseId])

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
      // Inside the knowledge-bases area the knowledge base is the address, so
      // choosing one is navigation and the current section is preserved.
      const target = knowledgeBaseSelectionTarget(location.pathname, id)
      if (target !== null) {
        navigate(target, { replace: true })
        return
      }
      // Elsewhere the page stays put; only its scope changes. Replace rather
      // than push so switching does not stack history entries.
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.set(KNOWLEDGE_BASE_SEARCH_PARAM, id)
          return next
        },
        { replace: true },
      )
    },
    [location.pathname, navigate, rememberKnowledgeBase, setSearchParams],
  )

  return {
    activeKnowledgeBaseId,
    knowledgeBases,
    isLoading: knowledgeBasesQuery.isLoading,
    isError: knowledgeBasesQuery.isError,
    setActiveKnowledgeBase,
  }
}
