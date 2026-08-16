import { useMemo } from 'react'
import type { ReactNode } from 'react'

import type { ValidationConfig } from '../../../api/contracts'
import { useUploadKnowledgeBaseDocuments } from '../../../api/knowledgebases'
import { showToast } from '../../../components/common/toastStore'
import { DocumentSourcePanel } from '../../../components/ingestion/DocumentSourcePanel'
import { apiErrorMessage } from '../../../lib/apiClient'
import type { ValidationIssue } from '../../../lib/ingestion/types'
import { validateDocumentFiles, validateIngestionPrerequisites } from '../../../lib/ingestion/validateIngestion'
import type { IngestionDraft } from '../../../stores/ingestionDraftStore'
import { countLabel } from '../../../utils/countLabel'
import type { UploadCallbacks } from './types'

type UseDocumentsFlowArgs = {
  knowledgeBaseId: string
  draft: IngestionDraft
  patchDraft: (patch: Partial<IngestionDraft>) => void
  clearDraft: (knowledgeBaseId: string) => void
  /** Called once the server has accepted a submission. */
  onSubmitted: () => void
  validation: ValidationConfig | undefined
  upload: UploadCallbacks
}

export type DocumentsFlowResult = {
  /** The document source panel, rendered in the "Choose a source" card. */
  panel: ReactNode
  /** Client-side validation issues for the currently staged files. */
  clientIssues: ValidationIssue[]
  canRunIngestion: boolean
  runPending: boolean
  error: unknown
  submit: () => void
}

/** Staging, validation, and submission for the document ingestion source. */
export function useDocumentsFlow({
  knowledgeBaseId,
  draft,
  patchDraft,
  clearDraft,
  onSubmitted,
  validation,
  upload,
}: UseDocumentsFlowArgs): DocumentsFlowResult {
  const uploadMutation = useUploadKnowledgeBaseDocuments(knowledgeBaseId)

  const documentIssues = useMemo(
    () => validateDocumentFiles(draft.pendingFiles, validation),
    [draft.pendingFiles, validation],
  )

  function runDocumentUpload(files: File[]) {
    upload.beginUpload(() => runDocumentUpload(files))
    uploadMutation.mutate(
      { files, onUploadProgress: upload.reportUploadProgress },
      {
        onSuccess: (response) => {
          const documentsLabel = countLabel(response.documents.length, 'document')

          upload.completeUpload()
          // The submission is the server's business from here: the run and its
          // receipt arrive through GET /workflows. Nothing about it stays in
          // this tab's draft.
          clearDraft(knowledgeBaseId)
          onSubmitted()
          showToast('success', `${documentsLabel} uploaded.`)
        },
        onError: (error) => {
          const message = apiErrorMessage(error, 'Document submission failed.')
          upload.failUpload(message)
          showToast('error', message)
        },
      },
    )
  }

  function submitDocuments() {
    const issues = [
      ...validateIngestionPrerequisites({
        knowledgeBaseId,
        sourceType: 'documents',
        feedName: draft.selectedFeedName,
      }),
      ...validateDocumentFiles(draft.pendingFiles, validation),
    ]

    if (issues.some((issue) => issue.severity === 'error')) {
      // Every issue here is already a live derivation of staged state (or
      // this knowledge base's prerequisites), recomputed into the validation
      // panel on every render. Writing it into the draft too would just
      // duplicate what is already showing.
      return
    }

    runDocumentUpload(draft.pendingFiles)
  }

  const canRunIngestion =
    draft.pendingFiles.length > 0 && documentIssues.every((issue) => issue.severity !== 'error')

  const panel = (
    <DocumentSourcePanel
      acceptContentTypes={validation?.allowed_content_types}
      files={draft.pendingFiles}
      onFilesChange={(files) => {
        patchDraft({ pendingFiles: files })
        patchDraft({ parseIssues: [] })
      }}
    />
  )

  return {
    panel,
    clientIssues: documentIssues,
    canRunIngestion,
    runPending: uploadMutation.isPending,
    error: uploadMutation.error,
    submit: submitDocuments,
  }
}
