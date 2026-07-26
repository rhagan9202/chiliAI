import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { RecordFeedConfig } from '../../../api/contracts'
import { RecordsSourcePanel } from '../RecordsSourcePanel'

const feeds: RecordFeedConfig[] = [
  {
    name: 'claims_feed',
    record_type: 'claim',
    source: 'file_upload',
    id_field: 'claim_id',
    record_schema: {
      claim_id: { type: 'string', display: 'Claim ID', required: true },
      provider_npi: { type: 'string', display: 'Provider NPI', required: true },
    },
    entities: [],
    relationships: [],
    observations: [],
  },
  {
    name: 'provider_feed',
    record_type: 'provider',
    source: 'api_push',
    id_field: 'provider_npi',
    record_schema: {},
    entities: [],
    relationships: [],
    observations: [],
  },
]

function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
}

describe('RecordsSourcePanel', () => {
  it('selects feeds, clears feed selection, and parses pasted JSONL records', () => {
    const onFeedChange = vi.fn()
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={onFeedChange}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="provider_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records feed'), {
      target: { value: 'provider_feed' },
    })
    fireEvent.change(screen.getByLabelText('Records feed'), {
      target: { value: '' },
    })
    fireEvent.change(screen.getByLabelText('Records format'), {
      target: { value: 'jsonl' },
    })
    fireEvent.change(screen.getByLabelText('Records content'), {
      target: {
        value: '{"claim_id":"c1","provider_npi":"1234567890"}\n{"claim_id":"c2","provider_npi":"2345678901"}',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Parse records' }))

    expect(onFeedChange).toHaveBeenCalledWith('provider_feed')
    expect(onFeedChange).toHaveBeenCalledWith(null)
    expect(onRowsParsed).toHaveBeenCalledWith(
      [
        { claim_id: 'c1', provider_npi: '1234567890' },
        { claim_id: 'c2', provider_npi: '2345678901' },
      ],
      [],
    )
    expect(screen.getByText('provider')).toBeInTheDocument()
    expect(screen.getByText('provider_npi')).toBeInTheDocument()
  })

  it('parses pasted CSV records from the parse button', () => {
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="provider_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records format'), {
      target: { value: 'csv' },
    })
    fireEvent.change(screen.getByLabelText('Records content'), {
      target: {
        value: 'claim_id,provider_npi,billed_amount\nc1,1234567890,99.50\nc2,2345678901,120.25\n',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Parse records' }))

    expect(onRowsParsed).toHaveBeenCalledWith(
      [
        { claim_id: 'c1', provider_npi: '1234567890', billed_amount: '99.50' },
        { claim_id: 'c2', provider_npi: '2345678901', billed_amount: '120.25' },
      ],
      [],
    )
  })

  it('auto-parses a selected CSV records file for file upload feeds', async () => {
    const onFileChange = vi.fn()
    const onDraftChange = vi.fn()
    const onRowsParsed = vi.fn()
    const file = new File(['claim_id,provider_npi\nc1,1234567890\n'], 'claims.csv', {
      type: 'text/csv',
    })

    const { rerender } = render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={onDraftChange}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [file] },
    })
    rerender(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={onDraftChange}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={file}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )
    expect(onFileChange).toHaveBeenCalledWith(file)
    expect(onDraftChange).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('claims.csv')).toBeInTheDocument()
    await waitFor(() => {
      expect(onRowsParsed).toHaveBeenCalledWith(
        [{ claim_id: 'c1', provider_npi: '1234567890' }],
        [],
      )
    })
    expect(await screen.findByText('Parsed for preview')).toBeInTheDocument()
  })

  it('auto-parses a selected JSONL records file for file upload feeds', async () => {
    const onFileChange = vi.fn()
    const onDraftChange = vi.fn()
    const onRowsParsed = vi.fn()
    const file = new File([
      '{"claim_id":"c1","provider_npi":"1234567890"}\n',
    ], 'claims.jsonl', {
      type: 'application/x-ndjson',
    })

    const { rerender } = render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={onDraftChange}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [file] },
    })
    rerender(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={onDraftChange}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={file}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    expect(onFileChange).toHaveBeenCalledWith(file)
    await waitFor(() => {
      expect(onRowsParsed).toHaveBeenCalledWith(
        [{ claim_id: 'c1', provider_npi: '1234567890' }],
        [],
      )
    })
  })

  it('shows a parsing empty-state hint after a file is selected', () => {
    const delayedText = createDeferred<string>()
    const file = new File(['claim_id,provider_npi\nc1,1234567890\n'], 'claims.csv', {
      type: 'text/csv',
    })
    Object.defineProperty(file, 'text', {
      value: vi.fn(() => delayedText.promise),
    })

    const { rerender } = render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={vi.fn()}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [file] },
    })
    rerender(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={vi.fn()}
        recordFile={file}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    expect(
      screen.getByText('Parsing the selected records file.'),
    ).toBeInTheDocument()
  })

  it('shows a file-picker hint for file upload feeds before a file is selected', () => {
    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={vi.fn()}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    expect(
      screen.getByText('Choose a CSV or JSONL records file to preview records automatically.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose file to parse' })).toBeDisabled()
  })

  it('does not parse empty pasted content for file-upload feeds without a selected file', () => {
    const onRowsParsed = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Choose file to parse' }))

    expect(onRowsParsed).not.toHaveBeenCalled()
    expect(screen.queryByText('CSV content is empty.')).not.toBeInTheDocument()
  })

  it('reports parse errors for unsupported selected file extensions', async () => {
    const onFileChange = vi.fn()
    const onRowsParsed = vi.fn()
    const file = new File(['hello'], 'claims.txt', { type: 'text/plain' })

    const { rerender } = render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [file] },
    })
    rerender(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={file}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    expect(onFileChange).toHaveBeenCalledWith(file)
    await waitFor(() => {
      expect(onRowsParsed).toHaveBeenCalledWith(
        [],
        [
          expect.objectContaining({
            id: 'parse-file-unsupported-record-format',
            message: 'Records file must use a .csv or .jsonl extension.',
          }),
        ],
      )
    })
    expect(await screen.findByText('Parse failed')).toBeInTheDocument()
  })

  it('invalidates parsed rows when pasted content or format changes', () => {
    const onDraftChange = vi.fn()

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={onDraftChange}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={vi.fn()}
        recordFile={null}
        rows={[{ claim_id: 'c1' }]}
        selectedFeedName="provider_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records content'), {
      target: { value: '{"provider_npi":"1234567890"}' },
    })
    fireEvent.change(screen.getByLabelText('Records format'), {
      target: { value: 'jsonl' },
    })

    expect(onDraftChange).toHaveBeenCalledTimes(2)
  })

  it('ignores delayed file parse results after the draft changes', async () => {
    const onDraftChange = vi.fn()
    const onFileChange = vi.fn()
    const onRowsParsed = vi.fn()
    const delayedText = createDeferred<string>()
    const firstFile = new File([''], 'claims-a.csv', { type: 'text/csv' })
    Object.defineProperty(firstFile, 'text', {
      value: vi.fn(() => delayedText.promise),
    })

    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={onDraftChange}
        onFileChange={onFileChange}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [firstFile] },
    })
    fireEvent.change(screen.getByLabelText('Records content'), {
      target: { value: 'claim_id,provider_npi\nc2,1234567890\n' },
    })
    delayedText.resolve('claim_id,provider_npi\nc1,1234567890\n')
    await delayedText.promise
    await Promise.resolve()

    expect(firstFile.text).toHaveBeenCalled()
    expect(onFileChange).toHaveBeenCalledWith(firstFile)
    expect(onDraftChange).toHaveBeenCalledTimes(2)
    expect(onRowsParsed).not.toHaveBeenCalled()
  })

  it('ignores delayed file parse results after unmount', async () => {
    const delayedText = createDeferred<string>()
    const onRowsParsed = vi.fn()
    const file = new File([''], 'claims.csv', { type: 'text/csv' })
    Object.defineProperty(file, 'text', {
      value: vi.fn(() => delayedText.promise),
    })

    const { unmount } = render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={onRowsParsed}
        recordFile={null}
        rows={[]}
        selectedFeedName="claims_feed"
      />,
    )

    fireEvent.change(screen.getByLabelText('Records file'), {
      target: { files: [file] },
    })
    unmount()
    delayedText.resolve('claim_id,provider_npi\nc1,1234567890\n')
    await delayedText.promise
    await Promise.resolve()

    expect(file.text).toHaveBeenCalled()
    expect(onRowsParsed).not.toHaveBeenCalled()
  })

  it('can hide inline preview table for unified review flow', () => {
    render(
      <RecordsSourcePanel
        feeds={feeds}
        issues={[]}
        onDraftChange={vi.fn()}
        onFileChange={vi.fn()}
        onFeedChange={vi.fn()}
        onRowsParsed={vi.fn()}
        recordFile={null}
        rows={[]}
        selectedFeedName="provider_feed"
        showPreviewTable={false}
      />,
    )

    expect(screen.queryByRole('table', { name: /records preview/i })).not.toBeInTheDocument()
  })
})
