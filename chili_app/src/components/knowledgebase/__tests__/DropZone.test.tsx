import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DropZone } from '../DropZone'

function makeFile(name: string, sizeBytes: number, type = 'text/plain'): File {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: sizeBytes })
  return file
}

describe('DropZone', () => {
  it('calls onFile when a valid file is dropped', () => {
    const onFile = vi.fn()
    render(<DropZone onFile={onFile} />)
    const zone = screen.getByTestId('drop-zone')
    const file = makeFile('docs.txt', 1000)
    fireEvent.drop(zone, {
      dataTransfer: { files: [file] },
    })
    expect(onFile).toHaveBeenCalledWith(file)
  })

  it('rejects files over the domain-config max_file_size_mb limit', () => {
    const onFile = vi.fn()
    const onValidationError = vi.fn()
    render(
      <DropZone
        onFile={onFile}
        onValidationError={onValidationError}
        validationConfig={{
          max_file_size_mb: 1,
          max_query_length: 10000,
          max_rag_question_length: 5000,
        }}
      />,
    )
    // 2 MB exceeds the configured 1 MB limit but is well under the 512 MB
    // fallback — proves the config value, not the fallback, drives rejection.
    const file = makeFile('big.pdf', 2 * 1024 * 1024, 'application/pdf')
    fireEvent.drop(screen.getByTestId('drop-zone'), {
      dataTransfer: { files: [file] },
    })
    expect(onFile).not.toHaveBeenCalled()
    expect(onValidationError).toHaveBeenCalledWith(
      expect.stringContaining('1 MB limit'),
    )
  })

  it('accepts a file within the domain-config limit that would fail a smaller hardcoded cap', () => {
    const onFile = vi.fn()
    const onValidationError = vi.fn()
    render(
      <DropZone
        onFile={onFile}
        onValidationError={onValidationError}
        validationConfig={{
          max_file_size_mb: 100,
          max_query_length: 10000,
          max_rag_question_length: 5000,
        }}
      />,
    )
    const file = makeFile('big.pdf', 60 * 1024 * 1024, 'application/pdf')
    fireEvent.drop(screen.getByTestId('drop-zone'), {
      dataTransfer: { files: [file] },
    })
    expect(onValidationError).not.toHaveBeenCalled()
    expect(onFile).toHaveBeenCalledWith(file)
  })

  it('falls back to the 512 MB platform default when no domain config is provided', () => {
    const onFile = vi.fn()
    const onValidationError = vi.fn()
    render(<DropZone onFile={onFile} onValidationError={onValidationError} />)
    const file = makeFile('huge.pdf', 513 * 1024 * 1024, 'application/pdf')
    fireEvent.drop(screen.getByTestId('drop-zone'), {
      dataTransfer: { files: [file] },
    })
    expect(onFile).not.toHaveBeenCalled()
    expect(onValidationError).toHaveBeenCalledWith(
      expect.stringContaining('512 MB limit'),
    )
  })

  it('rejects unsupported extensions', () => {
    const onFile = vi.fn()
    const onValidationError = vi.fn()
    render(
      <DropZone onFile={onFile} onValidationError={onValidationError} />,
    )
    const file = makeFile('app.exe', 1000, 'application/octet-stream')
    fireEvent.drop(screen.getByTestId('drop-zone'), {
      dataTransfer: { files: [file] },
    })
    expect(onFile).not.toHaveBeenCalled()
    expect(onValidationError).toHaveBeenCalled()
  })

  it('toggles the active state on dragover', () => {
    render(<DropZone onFile={() => undefined} />)
    const zone = screen.getByTestId('drop-zone')
    fireEvent.dragOver(zone)
    expect(zone).toHaveAttribute('data-active', 'true')
    fireEvent.dragLeave(zone)
    expect(zone).toHaveAttribute('data-active', 'false')
  })
})
