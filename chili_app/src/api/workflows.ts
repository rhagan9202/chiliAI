import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { WorkflowRunListResponse, WorkflowRunResponse } from './contracts'

export const workflowsQueryKey = ['workflows'] as const

export type WorkflowFilters = {
  knowledgeBaseId?: string
  status?: WorkflowRunResponse['status']
  limit?: number
  offset?: number
}

export function workflowsListQueryKey(filters: WorkflowFilters = {}) {
  return [workflowsQueryKey[0], filters] as const
}

export function getWorkflows(filters: WorkflowFilters = {}): Promise<WorkflowRunListResponse> {
  const params = new URLSearchParams()
  if (filters.knowledgeBaseId) {
    params.set('knowledge_base_id', filters.knowledgeBaseId)
  }
  if (filters.status) {
    params.set('status', filters.status)
  }
  if (filters.limit !== undefined) {
    params.set('limit', String(filters.limit))
  }
  if (filters.offset !== undefined) {
    params.set('offset', String(filters.offset))
  }

  const query = params.toString()
  return apiFetch<WorkflowRunListResponse>(query ? `/workflows?${query}` : '/workflows')
}

export function cancelWorkflow(workflowId: string): Promise<WorkflowRunResponse> {
  return apiFetch<WorkflowRunResponse>(`/workflows/${workflowId}/cancel`, { method: 'POST' })
}

export function useCancelWorkflow() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (workflowId: string) => cancelWorkflow(workflowId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: workflowsQueryKey })
    },
  })
}

export function useWorkflows(
  filters: WorkflowFilters = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: workflowsListQueryKey(filters),
    queryFn: () => getWorkflows(filters),
    enabled: options.enabled ?? true,
    refetchInterval: (query) => {
      const data = query.state.data
      return data?.items.some((workflow) => workflow.status === 'running' || workflow.status === 'queued')
        ? 3000
        : false
    },
  })
}