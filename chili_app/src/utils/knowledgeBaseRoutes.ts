/**
 * What a knowledge-base URL means.
 *
 * The URL is the single source of truth for which knowledge base and which
 * stage the analyst is looking at (spec §5). That only holds if every caller
 * agrees on the grammar, so the grammar lives here — deliberately free of
 * React and of react-router, so it is cheap to test and cannot drift with a
 * router upgrade.
 */

export const KNOWLEDGE_BASES_ROUTE = '/knowledge-bases'

export const WORKSPACE_SECTIONS = ['overview', 'add', 'data', 'runs', 'settings'] as const

export type WorkspaceSection = (typeof WORKSPACE_SECTIONS)[number]

const SECTION_SET: ReadonlySet<string> = new Set<string>(WORKSPACE_SECTIONS)

export function isWorkspaceSection(value: string | undefined): value is WorkspaceSection {
  return value !== undefined && SECTION_SET.has(value)
}

/** Overview is the workspace root: it has no section segment of its own. */
export function knowledgeBaseWorkspacePath(
  knowledgeBaseId: string,
  section: WorkspaceSection = 'overview',
): string {
  const base = `${KNOWLEDGE_BASES_ROUTE}/${encodeURIComponent(knowledgeBaseId)}`
  return section === 'overview' ? base : `${base}/${section}`
}

export type WorkspaceMatch = {
  knowledgeBaseId: string
  section: WorkspaceSection
}

function withoutTrailingSlash(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
}

/**
 * The knowledge base and section a path addresses, or null when the path is
 * not a workspace. An unknown section is *not* a workspace — it falls through
 * to the router's catch-all rather than being silently coerced to overview.
 */
export function matchWorkspacePath(pathname: string): WorkspaceMatch | null {
  const trimmed = withoutTrailingSlash(pathname)
  const prefix = `${KNOWLEDGE_BASES_ROUTE}/`
  if (!trimmed.startsWith(prefix)) {
    return null
  }

  const [rawId, section, ...rest] = trimmed.slice(prefix.length).split('/')
  if (!rawId || rest.length > 0) {
    return null
  }
  if (section !== undefined && !isWorkspaceSection(section)) {
    return null
  }

  const finalSection: WorkspaceSection = isWorkspaceSection(section) ? section : 'overview'
  return {
    knowledgeBaseId: decodeURIComponent(rawId),
    section: finalSection,
  }
}

/**
 * Where a pre-split `/knowledge-bases?kb=…` address should land now.
 *
 * Bookmarks, e-mailed links and every citation emitted before this phase use
 * the query-string form; they keep working by redirect rather than by the
 * library growing a second selection mechanism.
 */
export function legacyWorkspaceRedirect(search: URLSearchParams): string | null {
  const knowledgeBaseId = search.get('kb')
  if (!knowledgeBaseId) {
    return null
  }

  const documentId = search.get('document')
  if (!documentId) {
    return knowledgeBaseWorkspacePath(knowledgeBaseId)
  }

  const next = new URLSearchParams()
  next.set('document', documentId)
  const chunk = search.get('chunk')
  if (chunk !== null) {
    next.set('chunk', chunk)
  }
  return `${knowledgeBaseWorkspacePath(knowledgeBaseId, 'data')}?${next.toString()}`
}

/**
 * Where the app-wide knowledge-base picker should navigate when it is used on
 * `pathname`, or null when the selection is better expressed as `?kb=`.
 *
 * Inside the knowledge-bases area the KB *is* the address, so selecting one is
 * navigation (spec §1). Everywhere else the page stays put and only its scope
 * changes.
 */
export function knowledgeBaseSelectionTarget(
  pathname: string,
  knowledgeBaseId: string,
): string | null {
  const match = matchWorkspacePath(pathname)
  if (match) {
    return knowledgeBaseWorkspacePath(knowledgeBaseId, match.section)
  }
  if (withoutTrailingSlash(pathname) === KNOWLEDGE_BASES_ROUTE) {
    return knowledgeBaseWorkspacePath(knowledgeBaseId)
  }
  return null
}
