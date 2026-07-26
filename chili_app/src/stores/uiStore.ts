import { create } from 'zustand'

import { readPersisted, writePersisted } from './persistence'

/**
 * Where the analyst's active role is remembered between sessions. Without this
 * a reload silently demotes the user to the pack's default role, which then
 * bounces them off any page that role cannot open.
 */
export const SELECTED_ROLE_STORAGE_KEY = 'chiliai.selectedRole'

export function readStoredRole(): string | null {
  return readPersisted(SELECTED_ROLE_STORAGE_KEY)
}

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
  selectedRole: readStoredRole(),
  selectedEntityId: null,
  sidebarCollapsed: false,
  setLastRealtimeEventAt: (lastRealtimeEventAt) => set({ lastRealtimeEventAt }),
  setRealtimeConnected: (realtimeConnected) => set({ realtimeConnected }),
  setSelectedRole: (selectedRole) => {
    writePersisted(SELECTED_ROLE_STORAGE_KEY, selectedRole)
    set({ selectedRole })
  },
  toggleAiPanel: () => set((state) => ({ aiPanelOpen: !state.aiPanelOpen })),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  setSelectedEntityId: (selectedEntityId) => set({ selectedEntityId }),
}))
