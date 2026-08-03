import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { apiFetch, apiPatch, apiPost } from '../client'
import {
  acknowledgeAlert,
  alertDetailQueryKey,
  alertListQueryKey,
  alertsQueryKey,
  assignAlert,
  bulkUpdateAlertStatus,
  getAlerts,
  updateAlertStatus,
  useAssignAlert,
  useBulkUpdateAlertStatus,
  useUpdateAlertStatus,
} from '../alerts'
import type { AlertBulkStatusUpdateResponse, AlertOperationResponse } from '../contracts'

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
  apiPatch: vi.fn(),
  apiPost: vi.fn(),
}))

const apiFetchMock = vi.mocked(apiFetch)
const apiPatchMock = vi.mocked(apiPatch)
const apiPostMock = vi.mocked(apiPost)

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  })
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children)
  }
}

describe('alerts api', () => {
  it('exposes stable query keys for alert list/detail invalidation', () => {
    expect(alertsQueryKey).toEqual(['alerts'])
    expect(alertListQueryKey({ knowledgeBaseId: 'kb-1' })).toEqual([
      'alerts',
      { knowledgeBaseId: 'kb-1' },
    ])
    expect(alertDetailQueryKey('alert-1', 'kb-1')).toEqual(['alerts', 'kb-1', 'alert-1'])
  })

  it('serializes alert feed filters into backend query parameters', async () => {
    apiFetchMock.mockResolvedValueOnce({
      items: [],
      page: { page: 3, page_size: 25, total_items: 0 },
    })

    await getAlerts({
      knowledgeBaseId: 'kb-1',
      statuses: ['open', 'acknowledged'],
      severities: ['critical'],
      typologies: ['billing'],
      createdFrom: '2026-08-01',
      createdTo: '2026-08-03',
      evidence: 'with_evidence',
      freshness: 'fresh',
      limit: 25,
      offset: 50,
    })

    expect(apiFetchMock).toHaveBeenCalledWith(
      '/alerts?knowledge_base_id=kb-1&status=open&status=acknowledged&severity=critical&typology=billing&from=2026-08-01&to=2026-08-03&evidence=with_evidence&freshness=fresh&limit=25&offset=50',
    )
  })

  it('serializes assignment and status mutation payloads', async () => {
    const operationResponse = {
      status: 'accepted',
      alert: { id: 'alert-1' },
      audit_event: { event_type: 'status_changed' },
    } as AlertOperationResponse
    apiPatchMock.mockResolvedValue(operationResponse)

    const assignment: AlertOperationResponse = await assignAlert(
      'alert-1',
      'kb-1',
      'maya.patel@example.com',
    )
    const transition: AlertOperationResponse = await updateAlertStatus(
      'alert-1',
      'kb-1',
      'investigating',
      'Confirmed.',
    )

    expect(apiPatchMock).toHaveBeenNthCalledWith(1, '/alerts/alert-1/assignment', {
      knowledge_base_id: 'kb-1',
      assignee: 'maya.patel@example.com',
    })
    expect(apiPatchMock).toHaveBeenNthCalledWith(2, '/alerts/alert-1/status', {
      knowledge_base_id: 'kb-1',
      status: 'investigating',
      reason: 'Confirmed.',
    })
    expect(assignment.audit_event).toEqual({ event_type: 'status_changed' })
    expect(transition.audit_event).toEqual({ event_type: 'status_changed' })
  })

  it('serializes bulk status mutation payloads', async () => {
    const bulkResponse = {
      status: 'accepted',
      updated_alerts: [{ id: 'alert-1' }],
      rejected_alerts: [{ alert_id: 'alert-2', reason: 'invalid_transition' }],
    } as AlertBulkStatusUpdateResponse
    apiPostMock.mockResolvedValue(bulkResponse)

    const response: AlertBulkStatusUpdateResponse = await bulkUpdateAlertStatus(
      'kb-1',
      ['alert-1', 'alert-2'],
      'dismissed',
      'Duplicate.',
    )

    expect(apiPostMock).toHaveBeenCalledWith('/alerts/bulk/status', {
      knowledge_base_id: 'kb-1',
      alert_ids: ['alert-1', 'alert-2'],
      status: 'dismissed',
      reason: 'Duplicate.',
    })
    expect(response.rejected_alerts).toEqual([
      { alert_id: 'alert-2', reason: 'invalid_transition' },
    ])
  })

  it('exposes acknowledge audit receipts from the legacy route', async () => {
    const operationResponse = {
      status: 'accepted',
      alert: { id: 'alert-1' },
      audit_event: {
        event_type: 'status_changed',
        actor: 'anonymous',
        from_status: 'open',
        to_status: 'acknowledged',
      },
    } as AlertOperationResponse
    apiPostMock.mockResolvedValue(operationResponse)

    const response: AlertOperationResponse = await acknowledgeAlert('alert-1', 'kb-1')

    expect(apiPostMock).toHaveBeenCalledWith('/alerts/alert-1/acknowledge?knowledge_base_id=kb-1', {})
    expect(response.audit_event.to_status).toBe('acknowledged')
  })

  it('invalidates every alert query family after triage mutations', async () => {
    const queryClient = createTestQueryClient()
    vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()
    apiPatchMock.mockResolvedValue({ status: 'accepted' })
    apiPostMock.mockResolvedValue({ status: 'accepted' })

    const wrapper = createWrapper(queryClient)
    const assignHook = renderHook(() => useAssignAlert(), { wrapper })
    const statusHook = renderHook(() => useUpdateAlertStatus(), { wrapper })
    const bulkHook = renderHook(() => useBulkUpdateAlertStatus(), { wrapper })

    await act(async () => {
      await assignHook.result.current.mutateAsync({
        alertId: 'alert-1',
        knowledgeBaseId: 'kb-1',
        assignee: 'maya.patel@example.com',
      })
      await statusHook.result.current.mutateAsync({
        alertId: 'alert-1',
        knowledgeBaseId: 'kb-1',
        status: 'investigating',
      })
      await bulkHook.result.current.mutateAsync({
        knowledgeBaseId: 'kb-1',
        alertIds: ['alert-1'],
        status: 'dismissed',
      })
    })

    expect(queryClient.invalidateQueries).toHaveBeenCalledTimes(3)
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: alertsQueryKey })
  })
})
