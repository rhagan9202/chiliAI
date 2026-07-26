import { beforeEach, describe, expect, it } from 'vitest'

import {
  ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY,
  readStoredKnowledgeBaseId,
  useAppStore,
} from '../appStore'

describe('useAppStore', () => {
  beforeEach(() => {
    window.localStorage.clear()
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

  it('setActiveKnowledgeBase persists the selection so it survives a reload', () => {
    useAppStore.getState().setActiveKnowledgeBase('kb-7')

    expect(window.localStorage.getItem(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY)).toBe('kb-7')
  })

  it('setActiveKnowledgeBase(null) clears the persisted selection', () => {
    useAppStore.getState().setActiveKnowledgeBase('kb-7')
    useAppStore.getState().setActiveKnowledgeBase(null)

    expect(window.localStorage.getItem(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY)).toBeNull()
  })

  it('readStoredKnowledgeBaseId returns the persisted selection', () => {
    window.localStorage.setItem(ACTIVE_KNOWLEDGE_BASE_STORAGE_KEY, 'kb-from-last-session')

    expect(readStoredKnowledgeBaseId()).toBe('kb-from-last-session')
  })

  it('readStoredKnowledgeBaseId returns null when nothing was persisted', () => {
    expect(readStoredKnowledgeBaseId()).toBeNull()
  })
})
