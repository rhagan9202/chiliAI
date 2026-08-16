import { beforeEach, describe, expect, it } from 'vitest'

import {
  emptyDraft,
  hasStagedWork,
  useIngestionDraftStore,
} from '../ingestionDraftStore'

function file(name: string): File {
  return new File(['x'], name, { type: 'text/plain' })
}

describe('ingestionDraftStore', () => {
  beforeEach(() => {
    useIngestionDraftStore.getState().reset()
  })

  it('keeps each knowledge base’s staging to itself', () => {
    const { updateDraft } = useIngestionDraftStore.getState()
    updateDraft('kb-1', { pendingFiles: [file('a.txt')] })
    updateDraft('kb-2', { pendingFiles: [file('b.txt')] })

    const drafts = useIngestionDraftStore.getState().draftsByKb
    expect(drafts['kb-1'].pendingFiles.map((item) => item.name)).toEqual(['a.txt'])
    expect(drafts['kb-2'].pendingFiles.map((item) => item.name)).toEqual(['b.txt'])
  })

  it('clearing one draft leaves the others intact', () => {
    const { updateDraft, clearDraft } = useIngestionDraftStore.getState()
    updateDraft('kb-1', { pendingFiles: [file('a.txt')] })
    updateDraft('kb-2', { pendingFiles: [file('b.txt')] })

    clearDraft('kb-1')

    const drafts = useIngestionDraftStore.getState().draftsByKb
    expect(drafts['kb-1']).toBeUndefined()
    expect(drafts['kb-2'].pendingFiles).toHaveLength(1)
  })

  it('has no step state — stages are routes now', () => {
    expect('currentStep' in useIngestionDraftStore.getState()).toBe(false)
  })

  it('reports staged work for files, a records file, or parsed rows', () => {
    expect(hasStagedWork(emptyDraft())).toBe(false)
    expect(hasStagedWork({ ...emptyDraft(), pendingFiles: [file('a.txt')] })).toBe(true)
    expect(hasStagedWork({ ...emptyDraft(), pendingRecordFile: file('a.csv') })).toBe(true)
    expect(hasStagedWork({ ...emptyDraft(), parsedRows: [{ id: '1' }] })).toBe(true)
  })

  it('does not count a bare feed choice as staged work', () => {
    // Picking a feed and then leaving loses nothing worth a confirmation.
    expect(hasStagedWork({ ...emptyDraft(), selectedFeedName: 'claims' })).toBe(false)
  })
})
