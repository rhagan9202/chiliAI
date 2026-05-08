import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Alert } from '../../../types/api'
import { AlertTable } from '../AlertTable'
import type { SortDirection, SortField } from '../AlertTable'
import {
  ALERTS_QUERY_KEY_BASE,
  buildAlertsQueryKey,
} from '../../../hooks/useAlerts'

function makeAlert(overrides: Partial<Alert>): Alert {
  return {
    id: 'a1',
    entity_type: 'provider',
    entity_id: 'e1',
    severity: 'high',
    title: 'Suspicious billing',
    reasoning: 'Outlier upcoding rate',
    created_at: '2026-04-25T10:00:00Z',
    status: 'open',
    acknowledged: false,
    ...overrides,
  }
}

interface Harness {
  container: HTMLElement
  root: Root
  unmount: () => void
}

function mount(node: React.ReactElement): Harness {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return {
    container,
    root,
    unmount: () => {
      act(() => {
        root.unmount()
      })
      container.remove()
    },
  }
}

describe('AlertTable', () => {
  let harness: Harness | null = null

  beforeEach(() => {
    harness = null
  })

  afterEach(() => {
    harness?.unmount()
  })

  it('renders rows sorted by severity desc by default props', () => {
    const alerts: Alert[] = [
      makeAlert({ id: 'a1', severity: 'low' }),
      makeAlert({ id: 'a2', severity: 'critical' }),
      makeAlert({ id: 'a3', severity: 'medium' }),
    ]
    harness = mount(
      <AlertTable
        alerts={alerts}
        selectedIds={new Set()}
        onSelectionChange={() => {}}
        onRowClick={() => {}}
        sortField={'severity' satisfies SortField}
        sortDirection={'desc' satisfies SortDirection}
        onSortChange={() => {}}
      />,
    )
    const rows = harness.container.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(3)
    expect(rows[0].getAttribute('data-alert-id')).toBe('a2')
    expect(rows[2].getAttribute('data-alert-id')).toBe('a1')
  })

  it('toggles selection when a row checkbox is clicked', () => {
    const onSelectionChange = vi.fn<(next: Set<string>) => void>()
    const alerts: Alert[] = [makeAlert({ id: 'a1' }), makeAlert({ id: 'a2' })]
    harness = mount(
      <AlertTable
        alerts={alerts}
        selectedIds={new Set()}
        onSelectionChange={onSelectionChange}
        onRowClick={() => {}}
        sortField="severity"
        sortDirection="desc"
        onSortChange={() => {}}
      />,
    )
    const checkbox = harness.container.querySelector(
      'tbody tr:first-child input[type="checkbox"]',
    ) as HTMLInputElement
    act(() => {
      checkbox.click()
    })
    expect(onSelectionChange).toHaveBeenCalled()
    const argument = onSelectionChange.mock.calls[0][0]
    expect(argument.has('a1') || argument.has('a2')).toBe(true)
  })

  it('invokes onRowClick when a row body is clicked', () => {
    const onRowClick = vi.fn<(alert: Alert) => void>()
    const alerts: Alert[] = [makeAlert({ id: 'a1' })]
    harness = mount(
      <AlertTable
        alerts={alerts}
        selectedIds={new Set()}
        onSelectionChange={() => {}}
        onRowClick={onRowClick}
        sortField="severity"
        sortDirection="desc"
        onSortChange={() => {}}
      />,
    )
    const row = harness.container.querySelector(
      'tbody tr',
    ) as HTMLTableRowElement
    act(() => {
      row.click()
    })
    expect(onRowClick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'a1' }),
    )
  })
})

describe('useAlerts query keys', () => {
  it('changes the query key when filters change', () => {
    const baseKey = buildAlertsQueryKey({})
    const filteredKey = buildAlertsQueryKey({
      severity: ['critical'],
      status: 'open',
    })
    expect(baseKey).not.toEqual(filteredKey)
    expect(baseKey[0]).toBe(ALERTS_QUERY_KEY_BASE[0])
  })
})
