import { create } from 'zustand'

type UiState = {
  aiPanelOpen: boolean
  selectedEntityId: string | null
  sidebarCollapsed: boolean
  toggleAiPanel: () => void
  toggleSidebar: () => void
  setSelectedEntityId: (entityId: string | null) => void
}

export const useUiStore = create<UiState>((set) => ({
  aiPanelOpen: true,
  selectedEntityId: null,
  sidebarCollapsed: false,
  toggleAiPanel: () => set((state) => ({ aiPanelOpen: !state.aiPanelOpen })),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSelectedEntityId: (selectedEntityId) => set({ selectedEntityId }),
}))