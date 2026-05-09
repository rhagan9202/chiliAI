import { beforeEach, describe, expect, it } from 'vitest'

import { useAppStore } from '../appStore'

describe('useAppStore', () => {
  beforeEach(() => {
    useAppStore.setState({
      sidebarOpen: true,
      selectedEntityId: null,
      activeKnowledgeBaseId: null,
    })
  })

  it('exposes the documented initial state', () => {
    const state = useAppStore.getState()
    expect(state.sidebarOpen).toBe(true)
    expect(state.selectedEntityId).toBeNull()
    expect(state.activeKnowledgeBaseId).toBeNull()
  })

  it('toggleSidebar flips the sidebarOpen flag', () => {
    useAppStore.getState().toggleSidebar()
    expect(useAppStore.getState().sidebarOpen).toBe(false)
    useAppStore.getState().toggleSidebar()
    expect(useAppStore.getState().sidebarOpen).toBe(true)
  })

  it('selectEntity updates selectedEntityId', () => {
    useAppStore.getState().selectEntity('entity-42')
    expect(useAppStore.getState().selectedEntityId).toBe('entity-42')
    useAppStore.getState().selectEntity(null)
    expect(useAppStore.getState().selectedEntityId).toBeNull()
  })

  it('setActiveKnowledgeBase updates activeKnowledgeBaseId', () => {
    useAppStore.getState().setActiveKnowledgeBase('kb-1')
    expect(useAppStore.getState().activeKnowledgeBaseId).toBe('kb-1')
    useAppStore.getState().setActiveKnowledgeBase(null)
    expect(useAppStore.getState().activeKnowledgeBaseId).toBeNull()
  })
})
