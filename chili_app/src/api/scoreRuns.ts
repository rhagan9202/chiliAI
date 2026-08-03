import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  ScoreRunDetailResponse,
  ScoreRunListResponse,
  ScoreRunReplayRequest,
  ScoreRunStartRequest,
} from './contracts'

export type ScoreRunListOptions = {
  limit?: number
  offset?: number
}

export const scoreRunsQueryKey = (
  knowledgeBaseId: string | null,
  options: ScoreRunListOptions = {},
) => ['knowledge-bases', knowledgeBaseId, 'score-runs', options] as const

export const scoreRunQueryKey = (knowledgeBaseId: string | null, runId: string | null) =>
  ['knowledge-bases', knowledgeBaseId, 'score-runs', runId] as const

function scoreRunsPath(knowledgeBaseId: string): string {
  return `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/score-runs`
}

function scoreRunPath(knowledgeBaseId: string, runId: string): string {
  return `${scoreRunsPath(knowledgeBaseId)}/${encodeURIComponent(runId)}`
}

export function startScoreRun(
  knowledgeBaseId: string,
  payload: ScoreRunStartRequest,
): Promise<ScoreRunDetailResponse> {
  return apiPost<ScoreRunDetailResponse, ScoreRunStartRequest>(
    scoreRunsPath(knowledgeBaseId),
    payload,
  )
}

export function getScoreRuns(
  knowledgeBaseId: string,
  options: ScoreRunListOptions = {},
): Promise<ScoreRunListResponse> {
  const params = new URLSearchParams()
  if (options.limit !== undefined) {
    params.set('limit', String(options.limit))
  }
  if (options.offset !== undefined) {
    params.set('offset', String(options.offset))
  }
  const query = params.toString()
  return apiFetch<ScoreRunListResponse>(
    `${scoreRunsPath(knowledgeBaseId)}${query ? `?${query}` : ''}`,
  )
}

export function getScoreRun(
  knowledgeBaseId: string,
  runId: string,
): Promise<ScoreRunDetailResponse> {
  return apiFetch<ScoreRunDetailResponse>(scoreRunPath(knowledgeBaseId, runId))
}

export function cancelScoreRun(
  knowledgeBaseId: string,
  runId: string,
): Promise<ScoreRunDetailResponse> {
  return apiPost<ScoreRunDetailResponse, Record<string, never>>(
    `${scoreRunPath(knowledgeBaseId, runId)}/cancel`,
    {},
  )
}

export function replayScoreRun(
  knowledgeBaseId: string,
  runId: string,
  payload: ScoreRunReplayRequest = {},
): Promise<ScoreRunDetailResponse> {
  return apiPost<ScoreRunDetailResponse, ScoreRunReplayRequest>(
    `${scoreRunPath(knowledgeBaseId, runId)}/replay`,
    payload,
  )
}

export function useScoreRun(knowledgeBaseId: string | null, runId: string | null) {
  return useQuery({
    queryKey: scoreRunQueryKey(knowledgeBaseId, runId),
    queryFn: () => getScoreRun(knowledgeBaseId ?? '', runId ?? ''),
    enabled: Boolean(knowledgeBaseId && runId),
    refetchInterval: (query) => {
      const status = query.state.data?.run?.status
      return status === 'queued' || status === 'running' ? 3000 : false
    },
  })
}

export function useScoreRuns(
  knowledgeBaseId: string | null,
  options: ScoreRunListOptions = {},
) {
  return useQuery({
    queryKey: scoreRunsQueryKey(knowledgeBaseId, options),
    queryFn: () => getScoreRuns(knowledgeBaseId ?? '', options),
    enabled: Boolean(knowledgeBaseId),
    refetchInterval: (query) => {
      const activeRun = query.state.data?.items.some(
        (run) => run.status === 'queued' || run.status === 'running',
      )
      return activeRun ? 3000 : false
    },
  })
}

export function useStartScoreRun(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: ScoreRunStartRequest) => startScoreRun(knowledgeBaseId ?? '', payload),
    onSuccess: (detail) => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases', knowledgeBaseId, 'score-runs'] })
      queryClient.setQueryData(
        scoreRunQueryKey(knowledgeBaseId, detail.run.id),
        detail,
      )
    },
  })
}

export function useCancelScoreRun(knowledgeBaseId: string | null, runId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => cancelScoreRun(knowledgeBaseId ?? '', runId ?? ''),
    onSuccess: (detail) => {
      queryClient.setQueryData(scoreRunQueryKey(knowledgeBaseId, detail.run.id), detail)
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases', knowledgeBaseId, 'score-runs'] })
    },
  })
}

export function useReplayScoreRun(knowledgeBaseId: string | null, runId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: ScoreRunReplayRequest = {}) =>
      replayScoreRun(knowledgeBaseId ?? '', runId ?? '', payload),
    onSuccess: (detail) => {
      void queryClient.invalidateQueries({ queryKey: ['knowledge-bases', knowledgeBaseId, 'score-runs'] })
      queryClient.setQueryData(scoreRunQueryKey(knowledgeBaseId, detail.run.id), detail)
    },
  })
}
