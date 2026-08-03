import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  ExplanationReviewCreateRequest,
  ExplanationReviewListResponse,
  ExplanationReviewResponse,
} from './contracts'

export function evidencePackReviewsQueryKey(
  evidencePackId: string | null,
  knowledgeBaseId: string | null,
) {
  return ['evidence-pack-reviews', knowledgeBaseId ?? 'missing', evidencePackId ?? 'missing'] as const
}

export function listEvidencePackReviews(
  evidencePackId: string,
  knowledgeBaseId: string,
): Promise<ExplanationReviewListResponse> {
  const query = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<ExplanationReviewListResponse>(
    `/evidence-packs/${encodeURIComponent(evidencePackId)}/reviews?${query.toString()}`,
  )
}

export function createEvidencePackReview(
  evidencePackId: string,
  knowledgeBaseId: string,
  payload: ExplanationReviewCreateRequest,
): Promise<ExplanationReviewResponse> {
  const query = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiPost<ExplanationReviewResponse, ExplanationReviewCreateRequest>(
    `/evidence-packs/${encodeURIComponent(evidencePackId)}/reviews?${query.toString()}`,
    payload,
  )
}

export function useEvidencePackReviews(
  evidencePackId: string | null,
  knowledgeBaseId: string | null,
) {
  return useQuery({
    queryKey: evidencePackReviewsQueryKey(evidencePackId, knowledgeBaseId),
    queryFn: () => listEvidencePackReviews(evidencePackId ?? '', knowledgeBaseId ?? ''),
    enabled: Boolean(evidencePackId) && Boolean(knowledgeBaseId),
  })
}

export function useCreateEvidencePackReview() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      evidencePackId: string
      knowledgeBaseId: string
      payload: ExplanationReviewCreateRequest
    }) => createEvidencePackReview(vars.evidencePackId, vars.knowledgeBaseId, vars.payload),
    onSuccess: (_review, vars) => {
      void queryClient.invalidateQueries({
        queryKey: evidencePackReviewsQueryKey(vars.evidencePackId, vars.knowledgeBaseId),
      })
    },
  })
}
