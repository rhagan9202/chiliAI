import { useMemo, useState } from 'react'

import type { RecordFeedConfig } from '../../api/contracts'
import { parseCsvRecords, parseJsonlRecords } from '../../lib/ingestion/parseRecords'
import type { ValidationIssue } from '../../lib/ingestion/types'
import { RecordsPreviewTable } from './RecordsPreviewTable'
import './ingestion.css'

type RecordsFormat = 'csv' | 'jsonl'

type RecordsSourcePanelProps = {
  feeds: RecordFeedConfig[]
  selectedFeedName: string | null
  rows: Record<string, unknown>[]
  issues: ValidationIssue[]
  onFeedChange: (feedName: string | null) => void
  onRowsParsed: (rows: Record<string, unknown>[], issues: ValidationIssue[]) => void
}

function sourceLabel(source: RecordFeedConfig['source']): string {
  return source.replace(/_/g, ' ')
}

export function RecordsSourcePanel({
  feeds,
  selectedFeedName,
  rows,
  issues,
  onFeedChange,
  onRowsParsed,
}: RecordsSourcePanelProps) {
  const [format, setFormat] = useState<RecordsFormat>('csv')
  const [content, setContent] = useState('')

  const selectedFeed = useMemo(
    () => feeds.find((feed) => feed.name === selectedFeedName) ?? null,
    [feeds, selectedFeedName],
  )

  function parseRecords() {
    const result = format === 'csv'
      ? parseCsvRecords(content)
      : parseJsonlRecords(content)

    onRowsParsed(result.rows, result.errors)
  }

  return (
    <section className="ingestion-records-source" aria-labelledby="records-source-title">
      <div className="ingestion-source-panel__header">
        <h3 id="records-source-title" className="ingestion-source-panel__title">
          Records source
        </h3>
      </div>

      <div className="ingestion-records-source__controls">
        <label className="ingestion-source-panel__field">
          <span className="ingestion-source-panel__label">Records feed</span>
          <select
            className="ingestion-source-panel__control"
            aria-label="Records feed"
            value={selectedFeedName ?? ''}
            onChange={(event) => onFeedChange(event.currentTarget.value || null)}
          >
            <option value="">Select a feed</option>
            {feeds.map((feed) => (
              <option value={feed.name} key={feed.name}>
                {feed.name}
              </option>
            ))}
          </select>
        </label>

        <label className="ingestion-source-panel__field">
          <span className="ingestion-source-panel__label">Records format</span>
          <select
            className="ingestion-source-panel__control"
            aria-label="Records format"
            value={format}
            onChange={(event) => setFormat(event.currentTarget.value as RecordsFormat)}
          >
            <option value="csv">CSV</option>
            <option value="jsonl">JSONL</option>
          </select>
        </label>
      </div>

      {selectedFeed ? (
        <dl className="ingestion-feed-meta" aria-label="Selected feed metadata">
          <div className="ingestion-feed-meta__item">
            <dt>Record type</dt>
            <dd>{selectedFeed.record_type}</dd>
          </div>
          <div className="ingestion-feed-meta__item">
            <dt>Source</dt>
            <dd>{sourceLabel(selectedFeed.source)}</dd>
          </div>
          <div className="ingestion-feed-meta__item">
            <dt>ID field</dt>
            <dd>{selectedFeed.id_field}</dd>
          </div>
          <div className="ingestion-feed-meta__item">
            <dt>Schema fields</dt>
            <dd>{Object.keys(selectedFeed.record_schema).join(', ') || 'None'}</dd>
          </div>
        </dl>
      ) : null}

      <label className="ingestion-source-panel__field">
        <span className="ingestion-source-panel__label">Records content</span>
        <textarea
          className="ingestion-records-source__textarea"
          aria-label="Records content"
          value={content}
          rows={8}
          onChange={(event) => setContent(event.currentTarget.value)}
        />
      </label>

      <button className="ingestion-records-source__parse" type="button" onClick={parseRecords}>
        Parse records
      </button>

      <RecordsPreviewTable rows={rows} issues={issues} />
    </section>
  )
}
