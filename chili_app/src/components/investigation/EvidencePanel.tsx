import { useState } from 'react'

import type { EvidencePack } from '../../types/api'
import styles from './EvidencePanel.module.css'

export interface EvidencePanelProps {
  entityId: string | null
  evidence: EvidencePack[]
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  defaultCollapsed?: boolean
}

export function EvidencePanel({
  entityId,
  evidence,
  isLoading,
  isError,
  errorMessage,
  defaultCollapsed = false,
}: EvidencePanelProps): React.ReactElement {
  const [collapsed, setCollapsed] = useState<boolean>(defaultCollapsed)

  return (
    <section className={styles.panel} aria-label="Evidence">
      <header className={styles.header}>
        <h2 className={styles.title}>Evidence</h2>
        <button
          type="button"
          className={styles.toggle}
          onClick={() => setCollapsed((prev) => !prev)}
          aria-expanded={!collapsed}
          aria-controls="evidence-body"
        >
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </header>
      {!collapsed && (
        <div id="evidence-body" className={styles.body}>
          <p className={styles.notice}>
            Evidence Pack API endpoint
            <code> /investigation/entities/{'{'}entity_id{'}'}/evidence </code>
            is not yet implemented. Showing static placeholder data sourced
            from the alert pipeline.
          </p>
          {entityId === null && (
            <p className={styles.placeholder}>
              Select a node in the graph to view linked evidence.
            </p>
          )}
          {entityId !== null && isLoading && (
            <p className={styles.placeholder}>Loading evidence…</p>
          )}
          {entityId !== null && !isLoading && isError && (
            <p className={styles.placeholder} role="alert">
              {errorMessage ?? 'Failed to load evidence.'}
            </p>
          )}
          {entityId !== null && !isLoading && !isError && evidence.length === 0 && (
            <p className={styles.placeholder}>No evidence available.</p>
          )}
          {evidence.length > 0 && (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {evidence.map((pack) => (
                <li key={pack.id}>
                  <EvidenceItem pack={pack} />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

interface EvidenceItemProps {
  pack: EvidencePack
}

function EvidenceItem({ pack }: EvidenceItemProps): React.ReactElement {
  const [open, setOpen] = useState<boolean>(false)
  const confidencePct = Math.round(clamp01(pack.confidence) * 100)
  const summary = summarize(pack.reasoning)

  return (
    <article className={styles.item}>
      <button
        type="button"
        className={styles.itemHeader}
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className={styles.itemSummary}>
          <span className={styles.itemId}>{pack.id}</span>
          <span>{summary}</span>
        </span>
        <span className={styles.confidence}>
          <span
            className={styles.confidenceBar}
            role="meter"
            aria-valuenow={confidencePct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Confidence"
          >
            <span
              className={styles.confidenceFill}
              style={{ width: `${confidencePct}%` }}
            />
          </span>
          {confidencePct}%
        </span>
      </button>
      {open && (
        <div className={styles.itemBody}>
          <div>
            <strong>Reasoning</strong>
            <p style={{ margin: '4px 0 0' }}>{pack.reasoning}</p>
          </div>
          {pack.source_documents.length > 0 && (
            <div>
              <strong>Source documents</strong>
              <ul className={styles.refList}>
                {pack.source_documents.map((doc) => (
                  <li key={doc}>{doc}</li>
                ))}
              </ul>
            </div>
          )}
          {Object.keys(pack.scores).length > 0 && (
            <div>
              <strong>Scores</strong>
              <ul className={styles.scoreList}>
                {Object.entries(pack.scores).map(([key, value]) => (
                  <li key={key}>
                    {key}: {value.toFixed(2)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </article>
  )
}

function summarize(text: string, maxLen = 120): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen - 1).trimEnd() + '…'
}

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}
