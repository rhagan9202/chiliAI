import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { WorkflowRunListResponse } from './contracts'

export const workflowsQueryKey = ['workflows'] as const

export function getWorkflows(): Promise<WorkflowRunListResponse> {
  return apiFetch<WorkflowRunListResponse>('/workflows')
}

export function useWorkflows() {
  return useQuery({
    queryKey: workflowsQueryKey,
    queryFn: getWorkflows,
  })
}