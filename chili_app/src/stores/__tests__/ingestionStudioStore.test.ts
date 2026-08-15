import { beforeEach, describe, expect, it } from 'vitest'

import type { ValidationIssue } from '../../lib/ingestion/types'
import { emptyDraft, useIngestionStudioStore } from '../ingestionStudioStore'

const validationIssue: ValidationIssue = {
  id: 'issue-1',
  source: 'client',
  severity: 'error',
  message: 'Name is required',
  rowIndex: 0,
  field: 'name',
}

describe('ingestionStudioStore drafts are scoped by knowledge base', () => {
  beforeEach(() => {
    useIngestionStudioStore.getState().reset()
  })

  it('a draft staged for KB A never appears under KB B', () => {
    const file = new File(['x'], 'a.json', { type: 'application/json' })

    useIngestionStudioStore
      .getState()
      .updateDraft('kb-a', { pendingFiles: [file], sourceType: 'documents' })

    const state = useIngestionStudioStore.getState()
    expect(state.draftsByKb['kb-a']?.pendingFiles).toHaveLength(1)
    expect(state.draftsByKb['kb-b']).toBeUndefined()
  })

  it('clearDraft removes exactly one knowledge base draft', () => {
    const store = useIngestionStudioStore.getState()
    store.updateDraft('kb-a', { selectedFeedName: 'pde' })
    store.updateDraft('kb-b', { selectedFeedName: 'nppes_providers' })

    store.clearDraft('kb-a')

    const state = useIngestionStudioStore.getState()
    expect(state.draftsByKb['kb-a']).toBeUndefined()
    expect(state.draftsByKb['kb-b']?.selectedFeedName).toBe('nppes_providers')
  })

  it('addValidationIssues appends within the right draft', () => {
    const store = useIngestionStudioStore.getState()
    store.updateDraft('kb-a', {})
    store.updateDraft('kb-b', {})

    store.addValidationIssues('kb-a', [validationIssue])

    const state = useIngestionStudioStore.getState()
    expect(state.draftsByKb['kb-a']?.validationIssues).toHaveLength(1)
    expect(state.draftsByKb['kb-b']?.validationIssues).toHaveLength(0)
  })

  it('emptyDraft is the fallback shape', () => {
    expect(emptyDraft().pendingFiles).toEqual([])
    expect(emptyDraft().parsedRows).toEqual([])
    expect(emptyDraft().validationIssues).toEqual([])
    expect(emptyDraft().sourceType).toBeNull()
    expect(emptyDraft().selectedFeedName).toBeNull()
    expect(emptyDraft().pendingRecordFile).toBeNull()
  })

  it('reset drops every draft and returns the stepper to its first step', () => {
    const store = useIngestionStudioStore.getState()
    store.setCurrentStep('submit')
    store.updateDraft('kb-a', { parsedRows: [{ id: 'record-1' }] })

    store.reset()

    const state = useIngestionStudioStore.getState()
    expect(state.currentStep).toBe('knowledge-base')
    expect(state.draftsByKb).toEqual({})
  })

  it('emptyDraft hands out fresh arrays, so in-place mutation cannot leak', () => {
    const first = emptyDraft()
    first.pendingFiles.push(new File(['x'], 'a.json'))

    expect(emptyDraft().pendingFiles).toEqual([])
  })
})
