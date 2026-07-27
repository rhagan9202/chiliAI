import { parse as parseYaml, parseDocument } from 'yaml'

import type { ConfigValidationIssue } from '../../api/contracts'

function parseIssue(message: string): ConfigValidationIssue {
  return { message, error_type: 'parse_error', field: '', loc: [] }
}

/** Parse the editor buffer into the inline-content mapping for /config/validate. */
export function parseBufferToContent(
  buffer: string,
): { content: Record<string, unknown> } | { issue: ConfigValidationIssue } {
  let parsed: unknown
  try {
    parsed = parseYaml(buffer)
  } catch (error) {
    return {
      issue: parseIssue(
        error instanceof Error ? `YAML parse error: ${error.message}` : 'YAML parse error.',
      ),
    }
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { issue: parseIssue('A domain pack must be a YAML mapping at the top level.') }
  }
  return { content: parsed as Record<string, unknown> }
}

/** Character range of a value in the buffer, as CodeMirror wants it. */
export interface YamlRange {
  from: number
  to: number
}

/**
 * Locate the value a validation issue points at (UXA-404).
 *
 * The API returns `loc` as path segments (ints stringified). `getIn` accepts
 * string indices into sequences, so the path passes through unchanged. A node's
 * `range` is `[start, valueEnd, nodeEnd]`; the first two bound the value itself,
 * which is what should be selected — `nodeEnd` swallows the following comment
 * and whitespace.
 *
 * Returns null when there is nothing to point at: a file-level issue carries an
 * empty `loc`, and the buffer may have been edited since it was validated, so a
 * path that no longer resolves is a normal outcome rather than an error.
 */
export function locateInYaml(text: string, loc: readonly string[]): YamlRange | null {
  if (loc.length === 0) {
    return null
  }
  let node: unknown
  try {
    node = parseDocument(text).getIn(loc as unknown as (string | number)[], true)
  } catch {
    // A buffer that no longer parses has no locatable nodes at all.
    return null
  }
  if (node === null || node === undefined || typeof node !== 'object') {
    return null
  }
  const range = (node as { range?: [number, number, number] }).range
  if (!range) {
    return null
  }
  const [from, to] = range
  if (typeof from !== 'number' || typeof to !== 'number' || to < from) {
    return null
  }
  return { from, to }
}
