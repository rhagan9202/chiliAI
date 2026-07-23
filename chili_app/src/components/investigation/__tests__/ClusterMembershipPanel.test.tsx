import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ClusterResult } from '../../../api/contracts'
import { ClusterMembershipPanel } from '../ClusterMembershipPanel'

const clusters: ClusterResult[] = [
  { cluster_id: 'c-low', anomaly_score: 0.1, entity_ids: ['a'], label: null },
  { cluster_id: 'c-high', anomaly_score: 0.9, entity_ids: ['b', 'c'], label: 'dense referrals' },
]

describe('ClusterMembershipPanel', () => {
  it('orders by anomaly score desc and shows label, count, anomaly chip', () => {
    render(
      <ClusterMembershipPanel clusters={clusters} onSelectCluster={vi.fn()} selectedClusterId={null} />,
    )
    const rows = screen.getAllByTestId('cluster-row')
    expect(rows[0]).toHaveTextContent('dense referrals')
    expect(rows[0]).toHaveTextContent('2 members')
    expect(rows[0]).toHaveTextContent('90 anomaly')
  })

  it('toggles selection through onSelectCluster', () => {
    const onSelect = vi.fn()
    render(
      <ClusterMembershipPanel clusters={clusters} onSelectCluster={onSelect} selectedClusterId="c-high" />,
    )
    fireEvent.click(screen.getAllByTestId('cluster-row')[0])
    expect(onSelect).toHaveBeenCalledWith(null)
  })
})
