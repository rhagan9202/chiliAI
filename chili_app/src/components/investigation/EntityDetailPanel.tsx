import { useMemo, useState } from 'react'

import type { Entity, EntityProperties } from '../../types/api'
import { communityIdFor, riskScoreFor } from '../../utils/graphStyles'
import styles from './EntityDetailPanel.module.css'

export interface EntityDetailPanelProps {
  entity: Entity | null
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  defaultCollapsed?: boolean
}

export function EntityDetailPanel({
  entity,
  isLoading,
  isError,
  errorMessage,
  defaultCollapsed = false,
}: EntityDetailPanelProps): React.ReactElement {
  const [collapsed, setCollapsed] = useState<boolean>(defaultCollapsed)

  const riskScore = useMemo(
    () => (entity ? riskScoreFor(entity) : 0),
    [entity],
  )
  const communityId = useMemo(
    () => (entity ? communityIdFor(entity) : null),
    [entity],
  )
  const propertyEntries = useMemo(
    () => (entity ? extractDisplayProperties(entity.properties) : []),
    [entity],
  )

  return (
    <section className={styles.panel} aria-label="Entity detail">
      <header className={styles.header}>
        <h2 className={styles.title}>Entity Detail</h2>
        <button
          type="button"
          className={styles.toggle}
          onClick={() => setCollapsed((prev) => !prev)}
          aria-expanded={!collapsed}
          aria-controls="entity-detail-body"
        >
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </header>
      {!collapsed && (
        <div id="entity-detail-body" className={styles.body}>
          {isLoading && (
            <p className={styles.placeholder}>Loading entity…</p>
          )}
          {!isLoading && isError && (
            <p className={styles.error} role="alert">
              {errorMessage ?? 'Failed to load entity.'}
            </p>
          )}
          {!isLoading && !isError && entity === null && (
            <p className={styles.placeholder}>
              Select a node in the graph to view entity details.
            </p>
          )}
          {!isLoading && !isError && entity !== null && (
            <>
              <div className={styles.row}>
                <span className={styles.label}>Type</span>
                <span className={styles.value}>
                  <span className={styles.typeBadge}>{entity.type}</span>
                </span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>ID</span>
                <span className={styles.value}>{entity.id}</span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Risk score</span>
                <span className={styles.value}>
                  <RiskBar score={riskScore} />
                </span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Community</span>
                <span className={styles.value}>
                  {communityId ?? (
                    <span className={styles.empty}>not assigned</span>
                  )}
                </span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Created</span>
                <span className={styles.value}>
                  {formatTimestamp(entity.created_at)}
                </span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Updated</span>
                <span className={styles.value}>
                  {entity.updated_at ? (
                    formatTimestamp(entity.updated_at)
                  ) : (
                    <span className={styles.empty}>—</span>
                  )}
                </span>
              </div>
              <div className={styles.row}>
                <span className={styles.label}>Version</span>
                <span className={styles.value}>{entity.version}</span>
              </div>
              <div className={styles.section}>
                <div className={styles.sectionTitle}>Properties</div>
                {propertyEntries.length === 0 ? (
                  <span className={styles.empty}>No properties</span>
                ) : (
                  <table className={styles.propertyTable}>
                    <tbody>
                      {propertyEntries.map(([key, value]) => (
                        <tr key={key}>
                          <th scope="row">{key}</th>
                          <td>{value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  )
}

function RiskBar({ score }: { score: number }): React.ReactElement {
  const pct = Math.round(score * 100)
  return (
    <div className={styles.riskBar}>
      <div
        className={styles.riskTrack}
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={styles.riskFill} style={{ width: `${pct}%` }} />
      </div>
      <span>{pct}%</span>
    </div>
  )
}

function extractDisplayProperties(
  properties: EntityProperties,
): Array<readonly [string, string]> {
  const skip = new Set(['risk_score', 'community_id'])
  return Object.entries(properties)
    .filter(([key]) => !skip.has(key))
    .map(([key, value]) => [key, formatPropertyValue(value)] as const)
}

function formatPropertyValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().replace('T', ' ').slice(0, 19) + 'Z'
}
