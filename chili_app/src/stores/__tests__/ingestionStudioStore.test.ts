import { beforeEach, describe, expect, it } from 'vitest'

import type {
  IngestionReceiptEntry,
  ValidationIssue,
} from '../../lib/ingestion/types'
import { useIngestionStudioStore } from '../ingestionStudioStore'

const documentReceipt: IngestionReceiptEntry = {
  id: 'receipt-documents',
  sourceType: 'documents',
  status: 'accepted',
  message: 'Documents accepted',
  createdAt: '2026-05-16T12:00:00.000Z',
}

const recordReceipt: IngestionReceiptEntry = {
  id: 'receipt-records',
  sourceType: 'records',
  status: 'failed',
  message: 'Records failed validation',
  createdAt: '2026-05-16T12:05:00.000Z',
}

const validationIssue: ValidationIssue = {
  id: 'issue-1',
  source: 'client',
  severity: 'error',
  message: 'Name is required',
  rowIndex: 0,
  field: 'name',
}

describe('useIngestionStudioStore', () => {
  beforeEach(() => {
    useIngestionStudioStore.getState().reset()
  })

  it('exposes the documented initial state', () => {
    const state = useIngestionStudioStore.getState()

    expect(state.currentStep).toBe('knowledge-base')
    expect(state.sourceType).toBeNull()
    expect(state.selectedFeedName).toBeNull()
    expect(state.pendingFiles).toEqual([])
    expect(state.parsedRows).toEqual([])
    expect(state.validationIssues).toEqual([])
    expect(state.receipts).toEqual([])
    expect(state.activeTimelineEntryId).toBeNull()
  })

  it('updates step, source, feed, files, rows, and validation issues', () => {
    const file = new File(['claim_id,amount\n1,25'], 'claims.csv', {
      type: 'text/csv',
    })
    const rows = [{ claim_id: '1', amount: 25 }]
    const nextIssue: ValidationIssue = {
      id: 'issue-2',
      source: 'backend',
      severity: 'warning',
      message: 'Amount is unusually low',
      rowIndex: 0,
      field: 'amount',
    }

    useIngestionStudioStore.getState().setCurrentStep('validate')
    useIngestionStudioStore.getState().setSourceType('records')
    useIngestionStudioStore.getState().setSelectedFeedName('Claims CSV')
    useIngestionStudioStore.getState().setPendingFiles([file])
    useIngestionStudioStore.getState().setParsedRows(rows)
    useIngestionStudioStore.getState().setValidationIssues([validationIssue])
    useIngestionStudioStore.getState().addValidationIssues([nextIssue])
    useIngestionStudioStore.getState().setActiveTimelineEntryId('timeline-1')

    const state = useIngestionStudioStore.getState()
    expect(state.currentStep).toBe('validate')
    expect(state.sourceType).toBe('records')
    expect(state.selectedFeedName).toBe('Claims CSV')
    expect(state.pendingFiles).toEqual([file])
    expect(state.parsedRows).toEqual(rows)
    expect(state.validationIssues).toEqual([validationIssue, nextIssue])
    expect(state.activeTimelineEntryId).toBe('timeline-1')
  })

  it('prepends document and record receipts', () => {
    useIngestionStudioStore.getState().addReceipt(documentReceipt)
    useIngestionStudioStore.getState().addReceipt(recordReceipt)

    expect(useIngestionStudioStore.getState().receipts).toEqual([
      recordReceipt,
      documentReceipt,
    ])
  })

  it('reset clears draft state and receipts', () => {
    useIngestionStudioStore.getState().setCurrentStep('submit')
    useIngestionStudioStore.getState().setSourceType('documents')
    useIngestionStudioStore.getState().setSelectedFeedName('Policies')
    useIngestionStudioStore.getState().setPendingFiles([
      new File(['policy'], 'policy.pdf', { type: 'application/pdf' }),
    ])
    useIngestionStudioStore.getState().setParsedRows([{ id: 'record-1' }])
    useIngestionStudioStore.getState().setValidationIssues([validationIssue])
    useIngestionStudioStore.getState().addReceipt(documentReceipt)
    useIngestionStudioStore.getState().setActiveTimelineEntryId('timeline-2')

    useIngestionStudioStore.getState().reset()

    const state = useIngestionStudioStore.getState()
    expect(state.currentStep).toBe('knowledge-base')
    expect(state.sourceType).toBeNull()
    expect(state.selectedFeedName).toBeNull()
    expect(state.pendingFiles).toEqual([])
    expect(state.parsedRows).toEqual([])
    expect(state.validationIssues).toEqual([])
    expect(state.receipts).toEqual([])
    expect(state.activeTimelineEntryId).toBeNull()
  })

  it('reset returns clean fresh arrays after accidental in-place mutation', () => {
    useIngestionStudioStore.getState().reset()
    const pollutedPendingFiles = useIngestionStudioStore.getState().pendingFiles
    const pollutedParsedRows = useIngestionStudioStore.getState().parsedRows
    const pollutedValidationIssues =
      useIngestionStudioStore.getState().validationIssues
    const pollutedReceipts = useIngestionStudioStore.getState().receipts

    pollutedPendingFiles.push(
      new File(['policy'], 'mutated-policy.pdf', {
        type: 'application/pdf',
      }),
    )
    pollutedParsedRows.push({ id: 'mutated-record' })
    pollutedValidationIssues.push(validationIssue)
    pollutedReceipts.push(documentReceipt)

    useIngestionStudioStore.getState().reset()

    const state = useIngestionStudioStore.getState()
    expect(state.pendingFiles).toEqual([])
    expect(state.parsedRows).toEqual([])
    expect(state.validationIssues).toEqual([])
    expect(state.receipts).toEqual([])
    expect(state.pendingFiles).not.toBe(pollutedPendingFiles)
    expect(state.parsedRows).not.toBe(pollutedParsedRows)
    expect(state.validationIssues).not.toBe(pollutedValidationIssues)
    expect(state.receipts).not.toBe(pollutedReceipts)
  })
})
