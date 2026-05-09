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

  it('rejects oversized files via onValidationError', () => {
    const onFile = vi.fn()
    const onValidationError = vi.fn()
    render(
      <DropZone onFile={onFile} onValidationError={onValidationError} />,
    )
    const file = makeFile('big.pdf', 60 * 1024 * 1024, 'application/pdf')
    fireEvent.drop(screen.getByTestId('drop-zone'), {
      dataTransfer: { files: [file] },
    })
    expect(onFile).not.toHaveBeenCalled()
    expect(onValidationError).toHaveBeenCalled()
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
