import { useEffect, useMemo, useRef, useState } from 'react'

import type { RecordFeedConfig } from '../../api/contracts'
import { parseCsvRecords, parseJsonlRecords } from '../../lib/ingestion/parseRecords'
import type { ValidationIssue } from '../../lib/ingestion/types'
import { RecordsPreviewTable } from './RecordsPreviewTable'
import './ingestion.css'

type RecordsFormat = 'csv' | 'jsonl'
type ParseStatus = 'idle' | 'parsing' | 'parsed' | 'error'

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

function inferFileFormat(file: File): RecordsFormat | null {
  const lowerName = file.name.toLowerCase()
  if (lowerName.endsWith('.jsonl')) {
    return 'jsonl'
  }
  if (lowerName.endsWith('.csv')) {
    return 'csv'
  }
  return null
}

function parseRecordsContent(content: string, format: RecordsFormat) {
  return format === 'csv'
    ? parseCsvRecords(content)
    : parseJsonlRecords(content)
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
  const [parseStatus, setParseStatus] = useState<ParseStatus>('idle')
  const draftRevisionRef = useRef(0)

  const selectedFeed = useMemo(
    () => feeds.find((feed) => feed.name === selectedFeedName) ?? null,
    [feeds, selectedFeedName],
  )
  const isFileUploadFeed = selectedFeed?.source === 'file_upload'

  const emptyPreviewDescription = isFileUploadFeed
    ? recordFile
      ? parseStatus === 'parsing'
        ? 'Parsing the selected records file.'
        : parseStatus === 'error'
          ? 'No preview is available until the selected file parses successfully.'
          : 'The selected file will be parsed automatically for preview.'
      : 'Choose a CSV or JSONL records file to preview records automatically.'
    : 'Paste CSV or JSONL content and parse it to preview records.'

  useEffect(() => {
    return () => {
      draftRevisionRef.current += 1
    }
  }, [])

  function invalidateDraft() {
    draftRevisionRef.current += 1
    setParseStatus('idle')
    onDraftChange()
    return draftRevisionRef.current
  }

  async function parseRecords({
    auto = false,
    draftRevision = draftRevisionRef.current,
    sourceFile = recordFile,
  }: { auto?: boolean; draftRevision?: number; sourceFile?: File | null } = {}) {
    if (isFileUploadFeed && !sourceFile) {
      setParseStatus('error')
      onRowsParsed([], [
        {
          id: 'parse-file-missing-record-file',
          source: 'client',
          severity: 'error',
          kind: 'prerequisite',
          message: 'Choose a CSV or JSONL records file before parsing.',
        },
      ])
      return
    }

    const parseFormat = sourceFile ? inferFileFormat(sourceFile) : format

    if (!parseFormat) {
      setParseStatus('error')
      onRowsParsed([], [
        {
          id: 'parse-file-unsupported-record-format',
          source: 'client',
          severity: 'error',
          message: 'Records file must use a .csv or .jsonl extension.',
        },
      ])
      return
    }

    setParseStatus('parsing')
    let input: string
    try {
      input = sourceFile ? await readFileText(sourceFile) : content
    } catch (error) {
      if (draftRevision !== draftRevisionRef.current) {
        return
      }

      setParseStatus('error')
      onRowsParsed([], [
        {
          id: 'parse-file-read-failed',
          source: 'client',
          severity: 'error',
          message: error instanceof Error ? error.message : 'Records file could not be read.',
        },
      ])
      return
    }
    const result = parseRecordsContent(input, parseFormat)

    if (draftRevision !== draftRevisionRef.current) {
      return
    }

    setParseStatus(result.errors.length > 0 ? 'error' : 'parsed')
    onRowsParsed(result.rows, result.errors)

    if (auto && parseFormat !== format) {
      setFormat(parseFormat)
    }
  }

  const parseButtonLabel = isFileUploadFeed
    ? recordFile
      ? 'Re-parse file'
      : 'Choose file to parse'
    : 'Parse records'
  const parseButtonDisabled = parseStatus === 'parsing' || (isFileUploadFeed && !recordFile)

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
            invalidateDraft()
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
            invalidateDraft()
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
            const selectedFile = event.currentTarget.files?.[0] ?? null
            onFileChange(selectedFile)
            const draftRevision = invalidateDraft()
            if (isFileUploadFeed && selectedFile) {
              void parseRecords({ auto: true, draftRevision, sourceFile: selectedFile })
            }
          }}
        />
      </label>

      {recordFile ? (
        <div className="ingestion-records-source__selected-file">
          <span>{recordFile.name}</span>
          <span>{recordFile.type || 'unknown type'}</span>
          {parseStatus === 'parsing' ? <span role="status">Parsing…</span> : null}
          {parseStatus === 'parsed' ? <span>Parsed for preview</span> : null}
          {parseStatus === 'error' ? <span>Parse failed</span> : null}
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
            invalidateDraft()
          }}
        />
      </label>

      <button
        className="ingestion-records-source__parse"
        disabled={parseButtonDisabled}
        type="button"
        onClick={() => void parseRecords()}
      >
        {parseStatus === 'parsing' ? 'Parsing records' : parseButtonLabel}
      </button>

      <RecordsPreviewTable
        rows={rows}
        issues={issues}
        emptyDescription={emptyPreviewDescription}
      />
    </section>
  )
}
