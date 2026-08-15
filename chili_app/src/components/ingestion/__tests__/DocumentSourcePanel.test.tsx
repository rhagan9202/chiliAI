import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DocumentSourcePanel } from '../DocumentSourcePanel'

function makeFile(name: string): File {
  return new File(['x'], name, { type: 'application/json' })
}

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
    expect(within(list).getByText('11 B')).toBeInTheDocument()
    expect(within(list).getByText('scan.bin')).toBeInTheDocument()
    expect(within(list).getByText('unknown type')).toBeInTheDocument()
    expect(within(list).getByText('3 B')).toBeInTheDocument()
  })

  it('supports folder selection while preserving file selection behavior', () => {
    const onFilesChange = vi.fn()
    const folderFile = new File(['policy'], 'policy.md', { type: 'text/markdown' }) as File & {
      webkitRelativePath?: string
    }
    folderFile.webkitRelativePath = 'rules/policy.md'

    render(<DocumentSourcePanel files={[folderFile]} onFilesChange={onFilesChange} />)

    fireEvent.change(screen.getByLabelText('Document folder'), {
      target: { files: [folderFile] },
    })

    expect(onFilesChange).toHaveBeenCalledWith([folderFile])
    expect(screen.getByText('rules/policy.md')).toBeInTheDocument()
    expect(screen.getByText('6 B')).toBeInTheDocument()
  })
})

describe('DocumentSourcePanel staging', () => {
  it('appends new picks to the existing staged list', () => {
    const onFilesChange = vi.fn()
    const staged = [makeFile('a.json')]

    render(<DocumentSourcePanel files={staged} onFilesChange={onFilesChange} />)
    fireEvent.change(screen.getByLabelText('Document files'), {
      target: { files: [makeFile('b.json')] },
    })

    const next = onFilesChange.mock.calls[0]?.[0] as File[]
    expect(next.map((file) => file.name)).toEqual(['a.json', 'b.json'])
  })

  it('dedupes re-picks of an already staged file', () => {
    const onFilesChange = vi.fn()
    const a = makeFile('a.json')

    render(<DocumentSourcePanel files={[a]} onFilesChange={onFilesChange} />)
    fireEvent.change(screen.getByLabelText('Document files'), { target: { files: [a] } })

    expect((onFilesChange.mock.calls[0]?.[0] as File[]).length).toBe(1)
  })

  it('clears the input value so re-picking a corrected file still fires change', () => {
    render(<DocumentSourcePanel files={[]} onFilesChange={vi.fn()} />)
    const input = screen.getByLabelText('Document files') as HTMLInputElement

    fireEvent.change(input, { target: { files: [makeFile('a.json')] } })

    expect(input.value).toBe('')
  })

  it('removes a single staged file', async () => {
    const onFilesChange = vi.fn()

    render(
      <DocumentSourcePanel
        files={[makeFile('a.json'), makeFile('b.json')]}
        onFilesChange={onFilesChange}
      />,
    )
    await userEvent.click(screen.getAllByRole('button', { name: /remove/i })[0]!)

    expect((onFilesChange.mock.calls[0]?.[0] as File[]).map((file) => file.name)).toEqual([
      'b.json',
    ])
  })

  it('passes accept through to the file input', () => {
    render(
      <DocumentSourcePanel
        files={[]}
        onFilesChange={vi.fn()}
        acceptContentTypes={['application/pdf', 'text/csv']}
      />,
    )

    expect(screen.getByLabelText('Document files')).toHaveAttribute(
      'accept',
      'application/pdf,text/csv',
    )
    // Directory pickers ignore `accept`; claiming otherwise would be a lie.
    expect(screen.getByLabelText('Document folder')).not.toHaveAttribute('accept')
  })
})
