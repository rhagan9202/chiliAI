import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { ConnectionStatus } from '../components/common/ConnectionStatus'
import { LoadingSpinner } from '../components/common/LoadingSpinner'
import { AlertFilters } from '../components/alerts/AlertFilters'
import type { AlertFiltersValue } from '../components/alerts/AlertFilters'
import { AlertTable } from '../components/alerts/AlertTable'
import type {
  SortDirection,
  SortField,
} from '../components/alerts/AlertTable'
import {
  ALERTS_QUERY_KEY_BASE,
  useAcknowledgeAlerts,
  useAlerts,
  useDismissAlerts,
} from '../hooks/useAlerts'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAppStore } from '../stores/appStore'
import type { Alert } from '../types/api'
import type { WsEvent } from '../types/wsEvents'

import styles from '../components/alerts/AlertTable.module.css'

const INITIAL_FILTERS: AlertFiltersValue = {
  severities: [],
  status: '',
  entityType: '',
  startDate: '',
  endDate: '',
}

function withinDateRange(
  alert: Alert,
  startDate: string,
  endDate: string,
): boolean {
  if (!startDate && !endDate) {
    return true
  }
  const created = new Date(alert.created_at).getTime()
  if (Number.isNaN(created)) {
    return true
  }
  if (startDate) {
    const start = new Date(startDate).getTime()
    if (Number.isFinite(start) && created < start) {
      return false
    }
  }
  if (endDate) {
    const end = new Date(endDate).getTime() + 24 * 60 * 60 * 1000 - 1
    if (Number.isFinite(end) && created > end) {
      return false
    }
  }
  return true
}

export function AlertFeed(): React.ReactElement {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const selectEntity = useAppStore((state) => state.selectEntity)

  const [filters, setFilters] = useState<AlertFiltersValue>(INITIAL_FILTERS)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sortField, setSortField] = useState<SortField>('severity')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [resolveBy, setResolveBy] = useState<string>('analyst')

  const acknowledge = useAcknowledgeAlerts()
  const dismiss = useDismissAlerts()

  const query = useAlerts({
    severity: filters.severities.length > 0 ? filters.severities : undefined,
    status: filters.status ? filters.status : undefined,
    entity_type: filters.entityType ? filters.entityType : undefined,
  })

  const handleWsEvent = useCallback(
    (event: WsEvent): void => {
      if (event.event_type === 'alert.created') {
        void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_BASE })
      }
    },
    [queryClient],
  )

  const { status: wsStatus } = useWebSocket<WsEvent>('/ws/alerts', handleWsEvent)

  const items = useMemo(() => query.data?.items ?? [], [query.data])
  const filteredItems = useMemo(() => {
    return items.filter((alert) => {
      if (
        filters.severities.length > 0 &&
        !filters.severities.includes(alert.severity as 'critical')
      ) {
        return false
      }
      return withinDateRange(alert, filters.startDate, filters.endDate)
    })
  }, [items, filters])

  const entityTypeOptions = useMemo(() => {
    const set = new Set<string>()
    for (const alert of items) {
      set.add(alert.entity_type)
    }
    return Array.from(set).sort()
  }, [items])

  const handleSortChange = useCallback(
    (field: SortField): void => {
      if (field === sortField) {
        setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
      } else {
        setSortField(field)
        setSortDirection(field === 'severity' || field === 'created_at' ? 'desc' : 'asc')
      }
    },
    [sortField],
  )

  const handleRowClick = useCallback(
    (alert: Alert): void => {
      selectEntity(alert.entity_id)
      navigate(`/investigation?entity_id=${encodeURIComponent(alert.entity_id)}`)
    },
    [navigate, selectEntity],
  )

  const handleAcknowledge = useCallback((): void => {
    if (selectedIds.size === 0) {
      return
    }
    acknowledge.mutate(Array.from(selectedIds), {
      onSuccess: () => setSelectedIds(new Set()),
    })
  }, [acknowledge, selectedIds])

  const handleDismiss = useCallback((): void => {
    if (selectedIds.size === 0) {
      return
    }
    dismiss.mutate(
      {
        alertIds: Array.from(selectedIds),
        resolvedBy: resolveBy.trim() || 'analyst',
      },
      {
        onSuccess: () => setSelectedIds(new Set()),
      },
    )
  }, [dismiss, resolveBy, selectedIds])

  const isMutating = acknowledge.isPending || dismiss.isPending
  const disabled = selectedIds.size === 0 || isMutating

  return (
    <section className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Alert Feed</h1>
        <div className={styles.headerMeta}>
          <span>
            {filteredItems.length} of {query.data?.total ?? items.length} alerts
          </span>
          <ConnectionStatus status={wsStatus} />
        </div>
      </div>

      <AlertFilters
        value={filters}
        entityTypeOptions={entityTypeOptions}
        onChange={(next) => {
          setFilters(next)
          setSelectedIds(new Set())
        }}
      />

      <div className={styles.bulkBar} role="toolbar" aria-label="Bulk actions">
        <span>{selectedIds.size} selected</span>
        <button type="button" onClick={handleAcknowledge} disabled={disabled}>
          {acknowledge.isPending ? 'Acknowledging…' : 'Acknowledge'}
        </button>
        <button type="button" onClick={handleDismiss} disabled={disabled}>
          {dismiss.isPending ? 'Dismissing…' : 'Dismiss'}
        </button>
        <label className={styles.filterGroup}>
          <span>Resolved by</span>
          <input
            type="text"
            value={resolveBy}
            onChange={(event) => setResolveBy(event.target.value)}
            aria-label="Resolved by"
          />
        </label>
      </div>

      {query.isLoading ? (
        <LoadingSpinner label="Loading alerts…" />
      ) : query.isError ? (
        <div className={styles.error} role="alert">
          Failed to load alerts: {query.error.message}
        </div>
      ) : (
        <AlertTable
          alerts={filteredItems}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onRowClick={handleRowClick}
          sortField={sortField}
          sortDirection={sortDirection}
          onSortChange={handleSortChange}
        />
      )}
    </section>
  )
}

export default AlertFeed
