import { create } from 'zustand'

import type { IngestionSourceType, ValidationIssue } from '../lib/ingestion/types'

/**
 * In-flight staging work for one knowledge base.
 *
 * Three things are deliberately absent. `currentStep` is gone: stages are
 * routes, so the URL says where the analyst is. Backend errors are gone: they
 * belong to the mutation that produced them and clear when it is retried.
 * Derived validation is gone: document and row validation are pure functions of
 * the staged content, recomputed rather than stored. What remains is the work
 * itself — the handles and rows the analyst has assembled but not yet
 * submitted — keyed by the knowledge base it was assembled for, which is what
 * makes a cross-knowledge-base leak unrepresentable.
 */
export type IngestionDraft = {
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  /** Issues produced by the parse itself — an action's result, not a derivation. */
  parseIssues: ValidationIssue[]
}

export const emptyDraft = (): IngestionDraft => ({
  sourceType: null,
  selectedFeedName: null,
  pendingFiles: [],
  pendingRecordFile: null,
  parsedRows: [],
  parseIssues: [],
})

/** Whether leaving would lose something the analyst assembled. */
export function hasStagedWork(draft: IngestionDraft): boolean {
  return (
    draft.pendingFiles.length > 0 ||
    draft.pendingRecordFile !== null ||
    draft.parsedRows.length > 0
  )
}

type IngestionDraftState = {
  draftsByKb: Record<string, IngestionDraft>
  updateDraft: (kbId: string, patch: Partial<IngestionDraft>) => void
  clearDraft: (kbId: string) => void
  reset: () => void
}

export const useIngestionDraftStore = create<IngestionDraftState>((set) => ({
  draftsByKb: {},
  updateDraft: (kbId, patch) =>
    set((state) => ({
      draftsByKb: {
        ...state.draftsByKb,
        [kbId]: { ...(state.draftsByKb[kbId] ?? emptyDraft()), ...patch },
      },
    })),
  clearDraft: (kbId) =>
    set((state) => ({
      draftsByKb: Object.fromEntries(
        Object.entries(state.draftsByKb).filter(([key]) => key !== kbId),
      ),
    })),
  reset: () => set({ draftsByKb: {} }),
}))

// Stable identity so the selector below does not hand back a new object on
// every render (which would re-render its consumer in a loop).
const EMPTY_DRAFT_SINGLETON: IngestionDraft = emptyDraft()

/** The draft for the given knowledge base, or an empty draft when none is selected. */
export function useIngestionDraft(kbId: string | null): IngestionDraft {
  return useIngestionDraftStore((state) =>
    kbId ? state.draftsByKb[kbId] ?? EMPTY_DRAFT_SINGLETON : EMPTY_DRAFT_SINGLETON,
  )
}
