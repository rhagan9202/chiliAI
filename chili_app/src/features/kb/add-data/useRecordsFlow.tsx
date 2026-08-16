import { useMemo } from 'react'
import type { ReactNode } from 'react'

import type { RecordFeedConfig, RecordIngestReceipt } from '../../../api/contracts'
import { usePushRecords, useUploadRecordFile } from '../../../api/records'
import { showToast } from '../../../components/common/toastStore'
import { RecordsPreviewTable } from '../../../components/ingestion/RecordsPreviewTable'
import { RecordsSourcePanel } from '../../../components/ingestion/RecordsSourcePanel'
import { apiErrorMessage } from '../../../lib/apiClient'
import type { ValidationIssue } from '../../../lib/ingestion/types'
import {
  validateIngestionPrerequisites,
  validateRecordFile,
  validateRecordRows,
} from '../../../lib/ingestion/validateIngestion'
import type { IngestionDraft } from '../../../stores/ingestionDraftStore'
import type { UploadCallbacks } from './types'

type UseRecordsFlowArgs = {
  knowledgeBaseId: string
  draft: IngestionDraft
  patchDraft: (patch: Partial<IngestionDraft>) => void
  clearDraft: (knowledgeBaseId: string) => void
  /** Called once the server has accepted a submission. */
  onSubmitted: () => void
  feeds: RecordFeedConfig[]
  upload: UploadCallbacks
}

export type RecordsFlowResult = {
  /** The records source panel, rendered in the "Choose a source" card. */
  panel: ReactNode
  /** The parsed-rows preview, rendered in the "Review and submit" card. */
  reviewExtra: ReactNode
  /** Client-side validation issues for the currently staged rows. */
  clientIssues: ValidationIssue[]
  canRunIngestion: boolean
  runPending: boolean
  error: unknown
  submit: () => void
}

/** Staging, validation, and submission for the structured records source. */
export function useRecordsFlow({
  knowledgeBaseId,
  draft,
  patchDraft,
  clearDraft,
  onSubmitted,
  feeds,
  upload,
}: UseRecordsFlowArgs): RecordsFlowResult {
  const pushRecordsMutation = usePushRecords(knowledgeBaseId)
  const uploadRecordFileMutation = useUploadRecordFile(knowledgeBaseId)

  const selectedFeed = feeds.find((feed) => feed.name === draft.selectedFeedName) ?? null
  const recordIssues = useMemo(
    () =>
      selectedFeed
        ? validateRecordRows(selectedFeed, draft.parsedRows, {
            recordFile: draft.pendingRecordFile,
          })
        : [],
    [selectedFeed, draft.parsedRows, draft.pendingRecordFile],
  )

  function runRecordFileUpload(feedName: string, file: File) {
    upload.beginUpload(() => runRecordFileUpload(feedName, file))
    uploadRecordFileMutation.mutate(
      { feedName, file, onUploadProgress: upload.reportUploadProgress },
      {
        onSuccess: (receipt) => {
          upload.completeUpload()
          clearDraft(knowledgeBaseId)
          onSubmitted()
          showToast('success', receiptToastMessage(receipt))
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Records submission failed.')
          upload.failUpload(message)
          showToast('error', message)
        },
      },
    )
  }

  function submitRecords() {
    const recordFileIssues = selectedFeed?.source === 'file_upload'
      ? validateRecordFile(draft.pendingRecordFile)
      : []
    const issues = [
      ...validateIngestionPrerequisites({
        knowledgeBaseId,
        sourceType: 'records',
        feedName: draft.selectedFeedName,
      }),
      ...recordFileIssues,
      ...(selectedFeed
        ? validateRecordRows(selectedFeed, draft.parsedRows, {
            recordFile: draft.pendingRecordFile,
          })
        : []),
    ]

    if (issues.some((issue) => issue.severity === 'error') || !selectedFeed) {
      // Every issue here is already a live derivation of staged state (or
      // this knowledge base's prerequisites), recomputed into the validation
      // panel on every render. Writing it into the draft too would just
      // duplicate what is already showing.
      return
    }

    if (selectedFeed.source === 'file_upload') {
      const recordFile = draft.pendingRecordFile
      if (!recordFile) {
        // Unreachable from the UI: "Run ingestion" is disabled for a
        // file_upload feed until a record file is staged. Kept as a guard
        // rather than an assertion so a future caller of `submit` fails safe.
        return
      }
      runRecordFileUpload(selectedFeed.name, recordFile)
      return
    }

    pushRecordsMutation.mutate(
      {
        feed_name: selectedFeed.name,
        rows: draft.parsedRows,
      },
      {
        onSuccess: (receipt) => {
          clearDraft(knowledgeBaseId)
          onSubmitted()
          showToast('success', receiptToastMessage(receipt))
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Records submission failed.')
          showToast('error', message)
        },
      },
    )
  }

  const canRunIngestion =
    selectedFeed !== null &&
    (selectedFeed.source !== 'file_upload' || draft.pendingRecordFile !== null) &&
    draft.parsedRows.length > 0 &&
    recordIssues.every((issue) => issue.severity !== 'error')

  const panel = (
    <RecordsSourcePanel
      feeds={feeds}
      issues={recordIssues}
      showPreviewTable={false}
      onDraftChange={() => {
        patchDraft({ parsedRows: [] })
        patchDraft({ parseIssues: [] })
      }}
      onFileChange={(file) => {
        patchDraft({ pendingRecordFile: file })
      }}
      rows={draft.parsedRows}
      recordFile={draft.pendingRecordFile}
      selectedFeedName={draft.selectedFeedName}
      onFeedChange={(feedName) => {
        patchDraft({ selectedFeedName: feedName })
        patchDraft({ pendingRecordFile: null })
      }}
      onRowsParsed={(rows, parseIssues) => {
        patchDraft({ parsedRows: rows })
        patchDraft({ parseIssues })
      }}
    />
  )

  const reviewExtra = (
    <RecordsPreviewTable
      rows={draft.parsedRows}
      issues={recordIssues}
      emptyDescription="Parse records to review staged rows before running ingestion."
    />
  )

  return {
    panel,
    reviewExtra,
    clientIssues: recordIssues,
    canRunIngestion,
    runPending: pushRecordsMutation.isPending || uploadRecordFileMutation.isPending,
    // Precedence matches the pre-extraction page: the file-upload mutation's
    // error wins over the push mutation's, not the other way around.
    error: uploadRecordFileMutation.error ?? pushRecordsMutation.error,
    submit: submitRecords,
  }
}

function receiptToastMessage(receipt: RecordIngestReceipt): string {
  if (receipt.duplicate) {
    return `Duplicate submission for ${receipt.feed_name} (no-op).`
  }

  const parts = [`${receipt.accepted_count} accepted`]
  if (receipt.duplicate_count > 0) {
    parts.push(`${receipt.duplicate_count} duplicate`)
  }
  if (receipt.rejected_count > 0) {
    parts.push(`${receipt.rejected_count} rejected`)
  }
  return `${parts.join(', ')} for ${receipt.feed_name}.`
}
