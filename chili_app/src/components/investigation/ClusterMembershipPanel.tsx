import type { ClusterResult } from '../../api/contracts'
import { clusterColorFor } from '../../utils/graphStyles'
import { Chip } from '../ui/Chip'

export interface ClusterMembershipPanelProps {
  clusters: ClusterResult[]
  selectedClusterId: string | null
  onSelectCluster: (clusterId: string | null) => void
}

export function ClusterMembershipPanel({
  clusters,
  selectedClusterId,
  onSelectCluster,
}: ClusterMembershipPanelProps) {
  const ordered = [...clusters].sort(
    (a, b) =>
      b.anomaly_score - a.anomaly_score ||
      (b.entity_ids?.length ?? 0) - (a.entity_ids?.length ?? 0),
  )
  return (
    <div className="metric-stack" data-testid="cluster-membership-panel">
      <span className="flag-label">Clusters</span>
      {ordered.map((cluster) => {
        const selected = cluster.cluster_id === selectedClusterId
        return (
          <button
            className="metric-row"
            data-testid="cluster-row"
            key={cluster.cluster_id}
            onClick={() => onSelectCluster(selected ? null : cluster.cluster_id)}
            style={selected ? { outline: '1px solid var(--c-cyan)' } : undefined}
            type="button"
          >
            <span
              className="cluster-swatch"
              style={{ background: clusterColorFor(cluster.cluster_id) }}
            />
            <strong>{cluster.label ?? cluster.cluster_id}</strong>
            <span className="metric-row__label">
              {cluster.entity_ids?.length ?? 0} members
            </span>
            <Chip label={`${Math.round(cluster.anomaly_score * 100)} anomaly`} tone="warning" />
          </button>
        )
      })}
    </div>
  )
}
