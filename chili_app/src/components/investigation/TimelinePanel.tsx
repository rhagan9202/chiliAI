import { useMemo, useState } from 'react'

import type { Entity, TimelineEvent } from '../../types/api'

export interface TimelinePanelProps {
  entity: Entity | null
  events?: TimelineEvent[]
  defaultCollapsed?: boolean
}

interface DerivedEvent {
  id: string
  timestamp: string
  description: string
}

export function TimelinePanel({
  entity,
  events,
  defaultCollapsed = false,
}: TimelinePanelProps): React.ReactElement {
  const [collapsed, setCollapsed] = useState<boolean>(defaultCollapsed)
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')

  const derived: DerivedEvent[] = useMemo(() => {
    if (events && events.length > 0) {
      return events.map((evt) => ({
        id: evt.id,
        timestamp: evt.timestamp,
        description: `${evt.kind} — ${evt.description}`,
      }))
    }
    if (!entity) return []
    const out: DerivedEvent[] = [
      {
        id: `${entity.id}-created`,
        timestamp: entity.created_at,
        description: 'Entity created',
      },
    ]
    if (entity.updated_at) {
      out.push({
        id: `${entity.id}-updated`,
        timestamp: entity.updated_at,
        description: `Entity updated (v${entity.version})`,
      })
    }
    return out
  }, [entity, events])

  const sorted = useMemo(() => {
    const copy = [...derived]
    copy.sort((a, b) => {
      const ta = Date.parse(a.timestamp)
      const tb = Date.parse(b.timestamp)
      const safeA = Number.isNaN(ta) ? 0 : ta
      const safeB = Number.isNaN(tb) ? 0 : tb
      return order === 'desc' ? safeB - safeA : safeA - safeB
    })
    return copy
  }, [derived, order])

  return (
    <section
      style={{
        background: 'var(--bg, #fff)',
        border: '1px solid var(--border, #e5e4e7)',
        borderRadius: 8,
        overflow: 'hidden',
      }}
      aria-label="Entity timeline"
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid var(--border, #e5e4e7)',
          background: 'var(--bg-soft, #faf8fc)',
        }}
      >
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Timeline</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            onClick={() =>
              setOrder((prev) => (prev === 'desc' ? 'asc' : 'desc'))
            }
            disabled={sorted.length === 0}
            style={{
              background: 'transparent',
              border: '1px solid var(--border, #e5e4e7)',
              borderRadius: 4,
              padding: '2px 8px',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {order === 'desc' ? 'Newest first' : 'Oldest first'}
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((prev) => !prev)}
            aria-expanded={!collapsed}
            style={{
              background: 'transparent',
              border: '1px solid var(--border, #e5e4e7)',
              borderRadius: 4,
              padding: '2px 8px',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            {collapsed ? 'Expand' : 'Collapse'}
          </button>
        </div>
      </header>
      {!collapsed && (
        <div style={{ padding: '12px 16px' }}>
          {sorted.length === 0 ? (
            <p
              style={{
                margin: 0,
                fontSize: 13,
                color: 'var(--text, #6b6375)',
              }}
            >
              {entity
                ? 'No timeline events available.'
                : 'Select a node to view its timeline.'}
            </p>
          ) : (
            <ol
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {sorted.map((evt) => (
                <li
                  key={evt.id}
                  style={{
                    display: 'flex',
                    gap: 12,
                    fontSize: 13,
                    paddingLeft: 12,
                    borderLeft: '2px solid var(--accent, #aa3bff)',
                  }}
                >
                  <span
                    style={{
                      color: 'var(--text, #6b6375)',
                      whiteSpace: 'nowrap',
                      minWidth: 168,
                    }}
                  >
                    {formatTimestamp(evt.timestamp)}
                  </span>
                  <span style={{ color: 'var(--text-h, #08060d)' }}>
                    {evt.description}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  )
}

function formatTimestamp(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().replace('T', ' ').slice(0, 19) + 'Z'
}
