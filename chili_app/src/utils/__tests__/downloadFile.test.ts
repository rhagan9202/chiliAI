import { afterEach, describe, expect, it, vi } from 'vitest'

import { downloadTextFile, EXPORT_MIME_TYPES } from '../downloadFile'

describe('downloadTextFile', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('saves the content under the given name and cleans up after itself', () => {
    const createObjectURL = vi.fn(() => 'blob:fake')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const click = vi.fn()
    const anchor = document.createElement('a')
    anchor.click = click
    vi.spyOn(document, 'createElement').mockReturnValue(anchor)

    downloadTextFile('evidence-ev-1.md', '# Evidence', 'text/markdown')

    expect(anchor.download).toBe('evidence-ev-1.md')
    expect(anchor.href).toContain('blob:fake')
    expect(click).toHaveBeenCalledOnce()
    // The click is synchronous, so holding the blob past it only leaks.
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake')
    expect(document.querySelector('a')).toBeNull()

    vi.unstubAllGlobals()
  })
})

describe('EXPORT_MIME_TYPES', () => {
  it('covers every format the API can return', () => {
    expect(EXPORT_MIME_TYPES.markdown).toBe('text/markdown')
    expect(EXPORT_MIME_TYPES.json).toBe('application/json')
  })
})
