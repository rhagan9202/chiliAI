import { describe, expect, it } from 'vitest'

import { locateInYaml, parseBufferToContent } from '../packYaml'

const PACK = `domain:
  name: medicare_fraud
  display_name: Medicare Fraud Detection
entities:
  - name: provider
    display_label: Provider
  - name: claim
    display_label: Claim
`

/** What the buffer holds at a located range — the thing the editor selects. */
function slice(text: string, loc: string[]): string | null {
  const range = locateInYaml(text, loc)
  return range === null ? null : text.slice(range.from, range.to)
}

describe('locateInYaml', () => {
  it('locates a nested mapping value', () => {
    expect(slice(PACK, ['domain', 'name'])).toBe('medicare_fraud')
  })

  it('locates a value inside a sequence by its stringified index', () => {
    // The API sends loc segments as strings, including list indices.
    expect(slice(PACK, ['entities', '1', 'name'])).toBe('claim')
  })

  it('locates a whole sequence entry', () => {
    expect(slice(PACK, ['entities', '0'])).toContain('name: provider')
  })

  it('stops at the value, not the following line', () => {
    // range[2] would swallow the trailing newline and comment; range[1] is the
    // end of the value itself.
    expect(slice(PACK, ['domain', 'display_name'])).toBe('Medicare Fraud Detection')
  })

  it('returns null for a file-level issue with no path', () => {
    expect(locateInYaml(PACK, [])).toBeNull()
  })

  it('returns null for a path that is not in the buffer', () => {
    // The buffer may have been edited since it was validated.
    expect(locateInYaml(PACK, ['domain', 'nonexistent'])).toBeNull()
    expect(locateInYaml(PACK, ['entities', '9', 'name'])).toBeNull()
  })

  it('returns null when the buffer no longer parses', () => {
    expect(locateInYaml('domain:\n  - [unclosed\n', ['domain', 'name'])).toBeNull()
  })

  it('returns null for an empty buffer', () => {
    expect(locateInYaml('', ['domain'])).toBeNull()
  })
})

describe('parseBufferToContent', () => {
  it('returns the mapping for a valid pack', () => {
    const result = parseBufferToContent('domain:\n  name: x\n')
    expect(result).toEqual({ content: { domain: { name: 'x' } } })
  })

  it('rejects a non-mapping top level', () => {
    const result = parseBufferToContent('- one\n- two\n')
    expect('issue' in result && result.issue.error_type).toBe('parse_error')
  })

  it('reports a parse failure as a file-level issue', () => {
    const result = parseBufferToContent('domain:\n  - [unclosed\n')
    expect('issue' in result && result.issue.loc).toEqual([])
  })
})
