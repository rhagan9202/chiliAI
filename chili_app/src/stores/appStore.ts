import { create } from 'zustand'

import { readPersisted, writePersisted } from './persistence'

/**
 * Where the analyst's active knowledge base is remembered between sessions.
 * The selection is workspace context, not server state: it decides what every
 * KB-scoped page reads, so it has to survive a reload the same way the URL does.
 */
export const ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY = 'chiliai.activeKnowledgeBaseId'

/** Read the remembered selection; null when nothing is stored or readable. */
export function readStoredKnowledgeBaseId(): string | null {
  return readPersisted(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY)
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
    writePersisted(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY, id)
    set({ activeKnowledgeBaseId: id })
  },
}))
