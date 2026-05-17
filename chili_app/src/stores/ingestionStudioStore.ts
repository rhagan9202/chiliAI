import { create } from 'zustand'

import type {
  IngestionReceiptEntry,
  IngestionSourceType,
  IngestionStepId,
  ValidationIssue,
} from '../lib/ingestion/types'

type IngestionStudioStateValues = {
  currentStep: IngestionStepId
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  parsedRows: Record<string, unknown>[]
  validationIssues: ValidationIssue[]
  receipts: IngestionReceiptEntry[]
  activeTimelineEntryId: string | null
}

type IngestionStudioActions = {
  setCurrentStep: (currentStep: IngestionStepId) => void
  setSourceType: (sourceType: IngestionSourceType | null) => void
  setSelectedFeedName: (selectedFeedName: string | null) => void
  setPendingFiles: (pendingFiles: File[]) => void
  setParsedRows: (parsedRows: Record<string, unknown>[]) => void
  setValidationIssues: (validationIssues: ValidationIssue[]) => void
  addValidationIssues: (validationIssues: ValidationIssue[]) => void
  addReceipt: (receipt: IngestionReceiptEntry) => void
  setActiveTimelineEntryId: (activeTimelineEntryId: string | null) => void
  reset: () => void
}

export type IngestionStudioState = IngestionStudioStateValues &
  IngestionStudioActions

const initialState: IngestionStudioStateValues = {
  currentStep: 'knowledge-base',
  sourceType: null,
  selectedFeedName: null,
  pendingFiles: [],
  parsedRows: [],
  validationIssues: [],
  receipts: [],
  activeTimelineEntryId: null,
}

export const useIngestionStudioStore = create<IngestionStudioState>((set) => ({
  ...initialState,
  setCurrentStep: (currentStep) => set({ currentStep }),
  setSourceType: (sourceType) => set({ sourceType }),
  setSelectedFeedName: (selectedFeedName) => set({ selectedFeedName }),
  setPendingFiles: (pendingFiles) => set({ pendingFiles }),
  setParsedRows: (parsedRows) => set({ parsedRows }),
  setValidationIssues: (validationIssues) => set({ validationIssues }),
  addValidationIssues: (validationIssues) =>
    set((state) => ({
      validationIssues: [...state.validationIssues, ...validationIssues],
    })),
  addReceipt: (receipt) =>
    set((state) => ({ receipts: [receipt, ...state.receipts] })),
  setActiveTimelineEntryId: (activeTimelineEntryId) =>
    set({ activeTimelineEntryId }),
  reset: () => set({ ...initialState }),
}))
