import { create } from 'zustand'

import type {
  IngestionSourceType,
  IngestionStepId,
  ValidationIssue,
} from '../lib/ingestion/types'

/**
 * In-flight staging work for one knowledge base.
 *
 * This used to be a single global draft: staged `File` handles, parsed rows
 * and validation issues lived at the top of the store and were never cleared
 * when the analyst switched knowledge base. Files staged for KB A submitted
 * into KB B, and KB A's validation issues rendered against KB B's inventory.
 * Keying drafts by knowledge base makes that leak unrepresentable.
 */
export type IngestionDraft = {
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  validationIssues: ValidationIssue[]
}

export const emptyDraft = (): IngestionDraft => ({
  sourceType: null,
  selectedFeedName: null,
  pendingFiles: [],
  pendingRecordFile: null,
  parsedRows: [],
  validationIssues: [],
})

type IngestionStudioState = {
  /** Page chrome, not per-KB: the stepper describes where the analyst is looking. */
  currentStep: IngestionStepId
  draftsByKb: Record<string, IngestionDraft>
  setCurrentStep: (currentStep: IngestionStepId) => void
  updateDraft: (kbId: string, patch: Partial<IngestionDraft>) => void
  addValidationIssues: (kbId: string, issues: ValidationIssue[]) => void
  clearDraft: (kbId: string) => void
  reset: () => void
}

export const useIngestionStudioStore = create<IngestionStudioState>((set) => ({
  currentStep: 'knowledge-base',
  draftsByKb: {},
  setCurrentStep: (currentStep) => set({ currentStep }),
  updateDraft: (kbId, patch) =>
    set((state) => ({
      draftsByKb: {
        ...state.draftsByKb,
        [kbId]: { ...(state.draftsByKb[kbId] ?? emptyDraft()), ...patch },
      },
    })),
  addValidationIssues: (kbId, issues) =>
    set((state) => {
      const draft = state.draftsByKb[kbId] ?? emptyDraft()
      return {
        draftsByKb: {
          ...state.draftsByKb,
          [kbId]: { ...draft, validationIssues: [...draft.validationIssues, ...issues] },
        },
      }
    }),
  clearDraft: (kbId) =>
    set((state) => ({
      draftsByKb: Object.fromEntries(
        Object.entries(state.draftsByKb).filter(([key]) => key !== kbId),
      ),
    })),
  reset: () => set({ currentStep: 'knowledge-base', draftsByKb: {} }),
}))

// Stable identity so the selector below does not hand back a new object on
// every render (which would re-render the page in a loop).
const EMPTY_DRAFT_SINGLETON: IngestionDraft = emptyDraft()

/** The draft for the given knowledge base, or an empty draft when none is selected. */
export function useIngestionDraft(kbId: string | null): IngestionDraft {
  return useIngestionStudioStore((state) =>
    kbId ? state.draftsByKb[kbId] ?? EMPTY_DRAFT_SINGLETON : EMPTY_DRAFT_SINGLETON,
  )
}
