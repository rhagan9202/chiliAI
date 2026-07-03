import { parse as parseYaml } from 'yaml'

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
