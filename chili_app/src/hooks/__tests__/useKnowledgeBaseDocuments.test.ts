import { describe, expect, it } from 'vitest'

import type { ValidationConfig } from '../../api/contracts'
import {
  FALLBACK_MAX_FILE_SIZE_MB,
  validateDocumentFile,
} from '../useKnowledgeBaseDocuments'

function makeFile(name: string, sizeBytes: number, type = 'text/plain'): File {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: sizeBytes })
  return file
}

const validationConfig: ValidationConfig = {
  max_file_size_mb: 1,
  allowed_content_types: [],
  max_query_length: 10000,
  max_rag_question_length: 5000,
}

describe('validateDocumentFile', () => {
  it('rejects a file over the domain-config max_file_size_mb limit', () => {
    const file = makeFile('claims.pdf', 2 * 1024 * 1024, 'application/pdf')

    const result = validateDocumentFile(file, validationConfig)

    expect(result).toEqual({
      ok: false,
      reason: 'File exceeds the 1 MB limit (2.0 MB).',
    })
  })

  it('accepts a file under the domain-config limit', () => {
    const file = makeFile('claims.txt', 512 * 1024, 'text/plain')

    const result = validateDocumentFile(file, validationConfig)

    expect(result).toEqual({ ok: true })
  })

  it('falls back to FALLBACK_MAX_FILE_SIZE_MB (512 MB) when no config is provided', () => {
    const overLimit = makeFile(
      'huge.pdf',
      (FALLBACK_MAX_FILE_SIZE_MB + 1) * 1024 * 1024,
      'application/pdf',
    )
    const underLimit = makeFile('ok.pdf', 100 * 1024 * 1024, 'application/pdf')

    expect(validateDocumentFile(overLimit).ok).toBe(false)
    expect(validateDocumentFile(underLimit).ok).toBe(true)
  })

  it('falls back to FALLBACK_MAX_FILE_SIZE_MB when the config omits max_file_size_mb', () => {
    const overLimit = makeFile(
      'huge.pdf',
      (FALLBACK_MAX_FILE_SIZE_MB + 1) * 1024 * 1024,
      'application/pdf',
    )

    const result = validateDocumentFile(overLimit, null)

    expect(result.ok).toBe(false)
  })

  it('rejects unsupported file extensions regardless of size', () => {
    const file = makeFile('script.exe', 100, 'application/octet-stream')

    const result = validateDocumentFile(file, validationConfig)

    expect(result.ok).toBe(false)
    expect(result.reason).toContain('Unsupported file type')
  })
})
