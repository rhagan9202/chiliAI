import { useState } from 'react'
import { useOutletContext } from 'react-router'

import type { WorkspaceOutletContext } from '../../../pages/KnowledgeBaseWorkspacePage'
import { useWorkflows } from '../../../api/workflows'
import {
  useCancelScoreRun,
  useReplayScoreRun,
  useScoreRun,
  useScoreRuns,
  useStartScoreRun,
} from '../../../api/scoreRuns'
import { RunTimeline } from '../../../components/ingestion/RunTimeline'
import { ScoreRunStatusPanel } from '../../../components/knowledgebase/ScoreRunStatusPanel'
import { Card } from '../../../components/ui/Card'
import { EmptyState } from '../../../components/ui/EmptyState'

type RunsSectionProps = {
  knowledgeBaseId: string
  /** Score runs need something to score; the panel says so when this is 0. */
  entityCount: number
}

export function RunsSection({ knowledgeBaseId, entityCount }: RunsSectionProps) {
  const [selectedScoreRunId, setActiveScoreRunId] = useState<string | null>(null)
  const workflowsQuery = useWorkflows({ knowledgeBaseId })
  const scoreRunsQuery = useScoreRuns(knowledgeBaseId, { limit: 1 })
  const scoreRuns = scoreRunsQuery.data?.items ?? []
  const activeScoreRunId = selectedScoreRunId ?? scoreRuns[0]?.id ?? null
  const scoreRunQuery = useScoreRun(knowledgeBaseId, activeScoreRunId)
  const workflows = workflowsQuery.data?.items ?? []

  const startScoreRunMutation = useStartScoreRun(knowledgeBaseId)
  const cancelScoreRunMutation = useCancelScoreRun(knowledgeBaseId, activeScoreRunId)
  const replayScoreRunMutation = useReplayScoreRun(knowledgeBaseId, activeScoreRunId)

  const scoreRunStartDisabled = entityCount === 0
  // A disabled control explains itself in adjacent text, and the explanation
  // has to match the actual blocker (spec §3c).
  const scoreRunStartReason = scoreRunStartDisabled
    ? 'Start requires ingested entities in this knowledge base.'
    : null
  const scoreRunPendingAction = startScoreRunMutation.isPending
    ? 'start'
    : cancelScoreRunMutation.isPending
      ? 'cancel'
      : replayScoreRunMutation.isPending
        ? 'replay'
        : null

  return (
    <>
      <Card>
        {workflows.length > 0 ? (
          <RunTimeline workflows={workflows} />
        ) : (
          <EmptyState
            description="Submitting documents or records starts a run, and it appears here."
            title="No runs yet"
          />
        )}
      </Card>
      <Card>
        <ScoreRunStatusPanel
          detail={scoreRunQuery.data ?? null}
          disabled={false}
          error={scoreRunQuery.isError ? 'Score run status could not be loaded.' : null}
          loading={scoreRunQuery.isLoading}
          onCancel={() => {
            cancelScoreRunMutation.mutate(undefined, {
              onSuccess: (detail) => setActiveScoreRunId(detail.run.id),
            })
          }}
          onReplay={() => {
            replayScoreRunMutation.mutate(
              { idempotency_key: `score-replay:${activeScoreRunId ?? 'missing'}` },
              { onSuccess: (detail) => setActiveScoreRunId(detail.run.id) },
            )
          }}
          onStart={() => {
            if (scoreRunStartDisabled) {
              return
            }
            const currentRun = scoreRunQuery.data?.run
            startScoreRunMutation.mutate(
              {
                batch_size: 100,
                catalog_version: currentRun?.catalog_version ?? 'cms-fraud-features-v1',
                model_version: currentRun?.model_version ?? 'risk-linear-v1',
              },
              { onSuccess: (detail) => setActiveScoreRunId(detail.run.id) },
            )
          }}
          pendingAction={scoreRunPendingAction}
          startDisabled={scoreRunStartDisabled}
          startReason={scoreRunStartReason}
        />
      </Card>
    </>
  )
}

/** Route binding for `/knowledge-bases/:kbId/runs`. */
export function RunsRoute() {
  const { knowledgeBase } = useOutletContext<WorkspaceOutletContext>()
  return (
    <RunsSection entityCount={knowledgeBase.entity_count} knowledgeBaseId={knowledgeBase.id} />
  )
}
