import { beforeEach, describe, expect, it } from 'vitest'

import {
  SELECTED_ROLE_STORAGE_KEY,
  readStoredRole,
  useUiStore,
} from '../uiStore'

describe('useUiStore', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useUiStore.setState({ selectedRole: null })
  })

  it('setSelectedRole updates the selected role', () => {
    useUiStore.getState().setSelectedRole('supervisor')
    expect(useUiStore.getState().selectedRole).toBe('supervisor')
  })

  it('setSelectedRole persists the choice so a reload does not silently demote the user', () => {
    useUiStore.getState().setSelectedRole('supervisor')

    expect(window.localStorage.getItem(SELECTED_ROLE_STORAGE_KEY)).toBe('supervisor')
  })

  it('setSelectedRole(null) clears the persisted choice', () => {
    useUiStore.getState().setSelectedRole('supervisor')
    useUiStore.getState().setSelectedRole(null)

    expect(window.localStorage.getItem(SELECTED_ROLE_STORAGE_KEY)).toBeNull()
  })

  it('readStoredRole returns the role persisted by a previous session', () => {
    window.localStorage.setItem(SELECTED_ROLE_STORAGE_KEY, 'supervisor')

    expect(readStoredRole()).toBe('supervisor')
  })

  it('readStoredRole returns null when nothing was persisted', () => {
    expect(readStoredRole()).toBeNull()
  })
})
