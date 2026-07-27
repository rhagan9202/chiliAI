import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Scrapes the strings the app can actually put on screen so a test can assert
 * things about them in bulk.
 *
 * This is deliberately a scanner rather than a parser: it walks the source
 * character by character to (a) collect quoted-string and template-literal
 * contents and (b) blank out comments, then pulls JSX text nodes out of the
 * comment-free source. Comments must be excluded or the lint would flag the
 * implementation notes that legitimately name adapters and backends.
 */

export interface CopyOccurrence {
  file: string
  text: string
}

const SRC_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')

/** Directories whose strings are never rendered to a user. */
const EXCLUDED_DIRECTORIES = new Set(['__tests__', 'test', 'test-utils'])

/** Generated wire contracts — owned by the backend OpenAPI export, not by copy. */
const EXCLUDED_FILES = new Set([join('lib', 'api', 'schema.ts')])

interface ScanResult {
  /** Contents of every string literal and template-literal static span. */
  strings: string[]
  /** The source with every comment replaced by spaces, for JSX-text matching. */
  withoutComments: string
}

function scanSource(source: string): ScanResult {
  const strings: string[] = []
  const output: string[] = []
  let index = 0

  const pushBlank = (count: number): void => {
    output.push(' '.repeat(count))
  }

  while (index < source.length) {
    const char = source[index]
    const next = source[index + 1]

    if (char === '/' && next === '/') {
      const end = source.indexOf('\n', index)
      const stop = end === -1 ? source.length : end
      pushBlank(stop - index)
      index = stop
      continue
    }

    if (char === '/' && next === '*') {
      const end = source.indexOf('*/', index + 2)
      const stop = end === -1 ? source.length : end + 2
      // Preserve newlines so reported line numbers stay usable.
      output.push(source.slice(index, stop).replace(/[^\n]/g, ' '))
      index = stop
      continue
    }

    if (char === "'" || char === '"') {
      const quote = char
      let cursor = index + 1
      let literal = ''
      while (cursor < source.length && source[cursor] !== quote) {
        if (source[cursor] === '\\') {
          literal += source[cursor + 1] ?? ''
          cursor += 2
          continue
        }
        if (source[cursor] === '\n') break
        literal += source[cursor]
        cursor += 1
      }
      strings.push(literal)
      const stop = Math.min(cursor + 1, source.length)
      output.push(source.slice(index, stop))
      index = stop
      continue
    }

    if (char === '`') {
      let cursor = index + 1
      let literal = ''
      while (cursor < source.length && source[cursor] !== '`') {
        if (source[cursor] === '\\') {
          literal += source[cursor + 1] ?? ''
          cursor += 2
          continue
        }
        if (source[cursor] === '$' && source[cursor + 1] === '{') {
          // Skip the interpolated expression; only static spans are copy.
          let depth = 1
          cursor += 2
          while (cursor < source.length && depth > 0) {
            if (source[cursor] === '{') depth += 1
            if (source[cursor] === '}') depth -= 1
            cursor += 1
          }
          literal += ' '
          continue
        }
        literal += source[cursor]
        cursor += 1
      }
      strings.push(literal)
      const stop = Math.min(cursor + 1, source.length)
      output.push(source.slice(index, stop))
      index = stop
      continue
    }

    output.push(char ?? '')
    index += 1
  }

  return { strings, withoutComments: output.join('') }
}

/**
 * JSX text nodes: everything between a closing `>` — or the `}` that ends an
 * interpolation — and the next `<`. The `}` case matters because count copy is
 * written as `{n} document(s)`, where the noun follows the expression.
 */
function jsxTextNodes(source: string): string[] {
  const matches = source.matchAll(/[>}]([^<>{}]+)</g)
  return Array.from(matches, (match) => match[1] ?? '')
}

/**
 * A string is treated as prose when it has whitespace-separated words and does
 * not look like a route, URL, or identifier list. Code-ish strings such as
 * `'gnn-clusters'` or `/analytics/gnn/clusters` are excluded on that basis.
 */
function isProse(candidate: string): boolean {
  const text = candidate.trim()
  if (!/\s/.test(text)) return false
  if (!/[A-Za-z]{2}/.test(text)) return false
  if (/^(?:\.{0,2}\/|https?:)/.test(text)) return false
  return true
}

function sourceFiles(directory: string): string[] {
  const found: string[] = []
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const full = join(directory, entry.name)
    if (entry.isDirectory()) {
      if (EXCLUDED_DIRECTORIES.has(entry.name)) continue
      found.push(...sourceFiles(full))
      continue
    }
    if (!/\.tsx?$/.test(entry.name)) continue
    if (EXCLUDED_FILES.has(relative(SRC_ROOT, full))) continue
    found.push(full)
  }
  return found
}

function collect(keep: (candidate: string) => boolean): CopyOccurrence[] {
  const occurrences: CopyOccurrence[] = []
  for (const file of sourceFiles(SRC_ROOT)) {
    const scanned = scanSource(readFileSync(file, 'utf8'))
    const candidates = [...scanned.strings, ...jsxTextNodes(scanned.withoutComments)]
    for (const candidate of candidates) {
      if (!keep(candidate)) continue
      occurrences.push({ file: relative(SRC_ROOT, file).split(sep).join('/'), text: candidate.trim() })
    }
  }
  return occurrences
}

/** Every prose string the app can render, tagged with its `src/`-relative file. */
export function collectUserFacingCopy(): CopyOccurrence[] {
  return collect(isProse)
}

/**
 * Every extracted string, including single words the prose heuristic drops.
 * Use only for patterns no identifier can contain — the prose filter is what
 * keeps word-level rules from matching code, and this bypasses it.
 */
export function collectCopyCandidates(): CopyOccurrence[] {
  return collect((candidate) => candidate.trim().length > 0)
}
