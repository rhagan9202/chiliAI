import { create } from 'zustand'

type UiState = {
  aiPanelOpen: boolean
  lastRealtimeEventAt: string | null
  realtimeConnected: boolean
  selectedRole: string | null
  selectedEntityId: string | null
  sidebarCollapsed: boolean
  setLastRealtimeEventAt: (timestamp: string | null) => void
  setRealtimeConnected: (connected: boolean) => void
  setSelectedRole: (role: string | null) => void
  toggleAiPanel: () => void
  toggleSidebar: () => void
  setSelectedEntityId: (entityId: string | null) => void
}

export const useUiStore = create<UiState>((set) => ({
  aiPanelOpen: true,
  lastRealtimeEventAt: null,
  realtimeConnected: false,
  selectedRole: null,
  selectedEntityId: null,
  sidebarCollapsed: false,
  setLastRealtimeEventAt: (lastRealtimeEventAt) => set({ lastRealtimeEventAt }),
  setRealtimeConnected: (realtimeConnected) => set({ realtimeConnected }),
  setSelectedRole: (selectedRole) => set({ selectedRole }),
  toggleAiPanel: () => set((state) => ({ aiPanelOpen: !state.aiPanelOpen })),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSelectedEntityId: (selectedEntityId) => set({ selectedEntityId }),
}))