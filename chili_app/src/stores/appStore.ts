import { create } from 'zustand'

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
  activeKnowledgeBaseId: null,
  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  selectEntity: (id) => set({ selectedEntityId: id }),
  setActiveKnowledgeBase: (id) => set({ activeKnowledgeBaseId: id }),
}))
