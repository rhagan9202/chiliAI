import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DocumentSourcePanel } from '../DocumentSourcePanel'

describe('DocumentSourcePanel', () => {
  it('calls onFilesChange with uploaded files and previews selected file metadata', () => {
    const onFilesChange = vi.fn()
    const files = [
      new File(['policy text'], 'policy.txt', { type: 'text/plain' }),
      new File(['raw'], 'scan.bin'),
    ]

    render(<DocumentSourcePanel files={files} onFilesChange={onFilesChange} />)

    fireEvent.change(screen.getByLabelText('Document files'), {
      target: { files },
    })

    expect(onFilesChange).toHaveBeenCalledWith(files)

    const list = screen.getByRole('list', { name: /selected document files/i })
    expect(within(list).getByText('policy.txt')).toBeInTheDocument()
    expect(within(list).getByText('text/plain')).toBeInTheDocument()
    expect(within(list).getByText('scan.bin')).toBeInTheDocument()
    expect(within(list).getByText('unknown type')).toBeInTheDocument()
  })
})
