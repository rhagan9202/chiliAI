import { useState } from 'react'
import { useBlocker, useNavigate, useOutletContext } from 'react-router'

import type { WorkspaceOutletContext } from '../../../pages/KnowledgeBaseWorkspacePage'
import { knowledgeBaseWorkspacePath } from '../../../utils/knowledgeBaseRoutes'
import { useDomainConfig } from '../../../api/config'
import { ConfirmDialog } from '../../../components/status/ConfirmDialog'
import { SourceTypeStep } from '../../../components/ingestion/SourceTypeStep'
import { SubmitPanel } from '../../../components/ingestion/SubmitPanel'
import { UploadProgress } from '../../../components/ingestion/UploadProgress'
import type { UploadStatus } from '../../../components/ingestion/UploadProgress'
import { ValidationPanel } from '../../../components/ingestion/ValidationPanel'
import { Card } from '../../../components/ui/Card'
import { apiErrorMessage } from '../../../lib/apiClient'
import type { ValidationIssue } from '../../../lib/ingestion/types'
import { validateIngestionPrerequisites } from '../../../lib/ingestion/validateIngestion'
import {
  hasStagedWork,
  useIngestionDraft,
  useIngestionDraftStore,
} from '../../../stores/ingestionDraftStore'
import type { IngestionDraft } from '../../../stores/ingestionDraftStore'
import { useDocumentsFlow } from './useDocumentsFlow'
import { useRecordsFlow } from './useRecordsFlow'

type AddDataSectionProps = {
  knowledgeBaseId: string
  /** Called once the server has accepted a submission. */
  onSubmitted: () => void
}

export function AddDataSection({ knowledgeBaseId, onSubmitted }: AddDataSectionProps) {
  // Selector subscriptions only: a bare store read re-renders this whole flow
  // on every keystroke landing in any knowledge base's draft.
  const updateDraft = useIngestionDraftStore((state) => state.updateDraft)
  const clearDraft = useIngestionDraftStore((state) => state.clearDraft)
  const draft = useIngestionDraft(knowledgeBaseId)
  const domainConfigQuery = useDomainConfig()

  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle')
  const [uploadPercent, setUploadPercent] = useState(0)
  const [uploadError, setUploadError] = useState<string | null>(null)
  // Holds the last upload invocation so the Retry button can re-run it verbatim.
  const [retryUpload, setRetryUpload] = useState<(() => void) | null>(null)

  function patchDraft(patch: Partial<IngestionDraft>) {
    updateDraft(knowledgeBaseId, patch)
  }

  function beginUpload(retry: () => void) {
    setUploadStatus('uploading')
    setUploadPercent(0)
    setUploadError(null)
    setRetryUpload(() => retry)
  }

  function reportUploadProgress(percent: number) {
    setUploadPercent(percent)
  }

  function completeUpload() {
    setUploadStatus('done')
    setUploadPercent(100)
    setRetryUpload(null)
  }

  function failUpload(message: string) {
    setUploadStatus('error')
    setUploadError(message)
  }

  const feeds = domainConfigQuery.data?.records?.feeds ?? []
  const upload = { beginUpload, reportUploadProgress, completeUpload, failUpload }

  // Both flows are always mounted (their mutations and memoized validation
  // need to persist across a source-type switch); only the active one's
  // panel, issues, and submit are wired into the shared controls below.
  const documentsFlow = useDocumentsFlow({
    knowledgeBaseId,
    draft,
    patchDraft,
    clearDraft,
    onSubmitted,
    validation: domainConfigQuery.data?.validation,
    upload,
  })
  const recordsFlow = useRecordsFlow({
    knowledgeBaseId,
    draft,
    patchDraft,
    clearDraft,
    onSubmitted,
    feeds,
    upload,
  })

  const requiredIssues = validateIngestionPrerequisites({
    knowledgeBaseId,
    sourceType: draft.sourceType,
    feedName: draft.selectedFeedName,
  })
  const submitError = documentsFlow.error ?? recordsFlow.error
  // A backend rejection belongs to the mutation that produced it: it clears
  // when that mutation is retried, without anyone remembering to clear it.
  const backendIssues: ValidationIssue[] = submitError
    ? [
        {
          id: 'ingestion-backend-error',
          source: 'backend',
          severity: 'error',
          message: apiErrorMessage(submitError, 'Submission failed.'),
        },
      ]
    : []
  const currentIssues = [
    ...requiredIssues,
    ...(draft.sourceType === 'documents' ? documentsFlow.clientIssues : []),
    ...(draft.sourceType === 'records' ? recordsFlow.clientIssues : []),
    ...draft.parseIssues,
    ...backendIssues,
  ]

  const canRunIngestion =
    (draft.sourceType === 'documents' && documentsFlow.canRunIngestion) ||
    (draft.sourceType === 'records' && recordsFlow.canRunIngestion)
  const runPending = documentsFlow.runPending || recordsFlow.runPending

  const staged = hasStagedWork(draft)
  // The only place in this flow where leaving loses work. A submitted draft is
  // cleared before this can fire, so the prompt never appears after a success.
  // useBlocker only intercepts in-app navigation: a hard reload or a closed
  // tab still discards staging, and deliberately so — no beforeunload handler
  // is added, because a browser-chrome confirmation the app cannot word is
  // worse than none.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      staged && currentLocation.pathname !== nextLocation.pathname,
  )

  function runIngestion() {
    if (draft.sourceType === 'documents') {
      documentsFlow.submit()
      return
    }

    if (draft.sourceType === 'records') {
      recordsFlow.submit()
    }
  }

  return (
    <>
      <Card>
        <section aria-labelledby="add-data-source" className="ingestion-step-section">
          <div className="ingestion-step-section__header">
            <h2 id="add-data-source">Choose a source</h2>
            <p className="page-copy-block">
              Documents are parsed into chunks and entities. Structured records land in a
              configured feed.
            </p>
          </div>
          <SourceTypeStep
            selectedSourceType={draft.sourceType}
            onChange={(sourceType) => {
              patchDraft({ sourceType: sourceType })
            }}
          />

          {draft.sourceType === 'documents' ? documentsFlow.panel : null}
          {draft.sourceType === 'records' ? recordsFlow.panel : null}
        </section>
      </Card>

      <Card>
        <section aria-labelledby="add-data-review" className="ingestion-step-section">
          <div className="ingestion-step-section__header">
            <h2 id="add-data-review">Review and submit</h2>
          </div>

          {draft.sourceType === 'records' ? recordsFlow.reviewExtra : null}

          <ValidationPanel issues={currentIssues} />
          <SubmitPanel
            sourceType={draft.sourceType}
            canRunIngestion={canRunIngestion}
            runPending={runPending}
            onRunIngestion={runIngestion}
          />
          <UploadProgress
            label={
              draft.sourceType === 'documents'
                ? 'Document upload progress'
                : 'Records upload progress'
            }
            status={uploadStatus}
            percent={uploadPercent}
            error={uploadError ?? undefined}
            onRetry={() => retryUpload?.()}
          />
        </section>
      </Card>

      <ConfirmDialog
        body="The files and rows staged here have not been submitted. Leaving discards them."
        cancelLabel="Keep staging"
        confirmLabel="Discard"
        destructive
        onCancel={() => blocker.reset?.()}
        onConfirm={() => {
          clearDraft(knowledgeBaseId)
          blocker.proceed?.()
        }}
        open={blocker.state === 'blocked'}
        title="Discard staged files for this knowledge base?"
      />
    </>
  )
}

/**
 * Route binding for `/knowledge-bases/:kbId/add`. An accepted submission has a
 * consequence to watch, and Runs is where it is watched.
 */
export function AddDataRoute() {
  const navigate = useNavigate()
  const { knowledgeBase } = useOutletContext<WorkspaceOutletContext>()
  return (
    <AddDataSection
      knowledgeBaseId={knowledgeBase.id}
      onSubmitted={() => {
        navigate(knowledgeBaseWorkspacePath(knowledgeBase.id, 'runs'))
      }}
    />
  )
}
