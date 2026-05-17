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
  recordFile: File | null
  rows: Record<string, unknown>[]
  issues: ValidationIssue[]
  onDraftChange: () => void
  onFileChange: (file: File | null) => void
  onFeedChange: (feedName: string | null) => void
  onRowsParsed: (rows: Record<string, unknown>[], issues: ValidationIssue[]) => void
}

function sourceLabel(source: RecordFeedConfig['source']): string {
  return source.replace(/_/g, ' ')
}

function readFileText(file: File): Promise<string> {
  if ('text' in file && typeof file.text === 'function') {
    return file.text()
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

export function RecordsSourcePanel({
  feeds,
  selectedFeedName,
  recordFile,
  rows,
  issues,
  onDraftChange,
  onFileChange,
  onFeedChange,
  onRowsParsed,
}: RecordsSourcePanelProps) {
  const [format, setFormat] = useState<RecordsFormat>('csv')
  const [content, setContent] = useState('')

  const selectedFeed = useMemo(
    () => feeds.find((feed) => feed.name === selectedFeedName) ?? null,
    [feeds, selectedFeedName],
  )

  async function parseRecords() {
    const input = recordFile ? await readFileText(recordFile) : content
    const result = format === 'csv'
      ? parseCsvRecords(input)
      : parseJsonlRecords(input)

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
          onChange={(event) => {
            onFeedChange(event.currentTarget.value || null)
            onDraftChange()
          }}
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
          onChange={(event) => {
            setFormat(event.currentTarget.value as RecordsFormat)
            onDraftChange()
          }}
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
        <span className="ingestion-source-panel__label">Records file</span>
        <input
          className="ingestion-records-source__file"
          type="file"
          accept=".csv,.jsonl,text/csv,application/json,application/x-ndjson"
          aria-label="Records file"
          onChange={(event) => {
            onFileChange(event.currentTarget.files?.[0] ?? null)
            onDraftChange()
          }}
        />
      </label>

      {recordFile ? (
        <div className="ingestion-records-source__selected-file">
          <span>{recordFile.name}</span>
          <span>{recordFile.type || 'unknown type'}</span>
        </div>
      ) : null}

      <label className="ingestion-source-panel__field">
        <span className="ingestion-source-panel__label">Records content</span>
        <textarea
          className="ingestion-records-source__textarea"
          aria-label="Records content"
          value={content}
          rows={8}
          onChange={(event) => {
            setContent(event.currentTarget.value)
            onDraftChange()
          }}
        />
      </label>

      <button className="ingestion-records-source__parse" type="button" onClick={() => void parseRecords()}>
        Parse records
      </button>

      <RecordsPreviewTable rows={rows} issues={issues} />
    </section>
  )
}
