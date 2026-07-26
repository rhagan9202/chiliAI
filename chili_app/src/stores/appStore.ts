import { create } from 'zustand'

/**
 * Where the analyst's active knowledge base is remembered between sessions.
 * The selection is workspace context, not server state: it decides what every
 * KB-scoped page reads, so it has to survive a reload the same way the URL does.
 */
export const ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY = 'chiliai.activeKnowledgeBaseId'

/**
 * Read the remembered selection. Storage can be unavailable (private mode,
 * disabled cookies, non-browser test envs); an unreadable store is treated as
 * "nothing remembered" rather than an error, because the caller can always fall
 * back to the default knowledge base.
 */
export function readStoredKnowledgeBaseId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY)
  } catch {
    return null
  }
}

function persistKnowledgeBaseId(id: string | null): void {
  try {
    if (id === null) {
      window.localStorage.removeItem(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY, id)
  } catch {
    // A failed write only costs the user their selection on the next reload.
  }
}

export interface AppState {
  sidebarOpen: boolean
  selectedEntityId: string | null
  activeKnowledgeBaseId: string | null
  toggleSidebar: () => void
  selectEntity: (id: string | null) => void
  setActiveKnowledgeBase: (id: string | null) => void
}

export const useAppStore = create<AppState>((set) => ({
  sidebarOpen: true,
  selectedEntityId: null,
  activeKnowledgeBaseId: readStoredKnowledgeBaseId(),
  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  selectEntity: (id) => set({ selectedEntityId: id }),
  setActiveKnowledgeBase: (id) => {
    persistKnowledgeBaseId(id)
    set({ activeKnowledgeBaseId: id })
  },
}))
