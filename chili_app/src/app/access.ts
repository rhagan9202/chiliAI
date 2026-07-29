import type { DomainConfig, DomainFeatures } from '../api/contracts'

/**
 * Routes this SPA implements that correspond to a domain-pack page id.
 *
 * A pack decides which of these its analysts get. Anything a pack does not
 * declare must be refused rather than rendered: `/housing` is a real page here,
 * so without this table it slipped through the "no configured page matched, so
 * no opinion" branch and served Air Force content under a Medicare pack.
 *
 * Detail routes that hang off a page (`/scorecards/:runId`, reached from the
 * housing dashboard) are deliberately absent — they are not nav pages and are
 * governed by the page that links to them.
 */
const PACK_PAGE_ROUTES: ReadonlyMap<string, string> = new Map([
  ['/dashboard', 'dashboard'],
  ['/alerts', 'alerts'],
  ['/investigation', 'investigation'],
  ['/cases', 'cases'],
  ['/knowledge-bases', 'knowledge_bases'],
  ['/policy', 'policy'],
  ['/housing', 'housing'],
  ['/rag-chat', 'rag_chat'],
  ['/configuration', 'configuration'],
])

function normalizePath(pathname: string): string {
  return pathname.endsWith('/') && pathname !== '/' ? pathname.slice(0, -1) : pathname
}

/** The pack page id a path belongs to, matching sub-paths to their parent. */
function packPageIdForPath(pathname: string): string | null {
  const normalized = normalizePath(pathname)
  for (const [route, pageId] of PACK_PAGE_ROUTES) {
    if (normalized === route || normalized.startsWith(`${route}/`)) {
      return pageId
    }
  }
  return null
}

export function getDefaultRole(features?: DomainFeatures) {
  if (!features) {
    return null
  }

  return features.default_role ?? Object.keys(features.roles)[0] ?? null
}

/**
 * The role the workspace should act as.
 *
 * A role remembered from a previous session outranks the pack default, but only
 * if the active pack actually defines it. Switching packs leaves the previous
 * pack's role behind, and treating that as "no role" used to collapse gating to
 * pack level — so a role that did not exist out-ranked every real restricted
 * role. Anything unrecognised resolves to the pack default instead.
 */
export function resolveRole(
  features: DomainFeatures | undefined,
  requestedRole: string | null,
): string | null {
  if (!features) {
    return null
  }
  if (requestedRole !== null && features.roles[requestedRole]) {
    return requestedRole
  }
  return getDefaultRole(features)
}

export function getAllowedPageIds(
  features: DomainFeatures | undefined,
  selectedRole: string | null,
) {
  if (!features) {
    return [] as string[]
  }

  const enabledPages = new Set(features.enabled_pages)
  const roleId = resolveRole(features, selectedRole)
  const role = roleId !== null ? features.roles[roleId] : undefined
  // Only a pack that declares no roles at all falls back to every enabled page.
  if (!role) {
    return [...enabledPages]
  }

  return role.pages.filter((pageId) => enabledPages.has(pageId))
}

export function getLandingRoute(
  domainConfig: DomainConfig | undefined,
  features: DomainFeatures | undefined,
  selectedRole: string | null,
) {
  const navigationPages = domainConfig?.ui?.navigation?.pages ?? []
  const allowedPageIds = getAllowedPageIds(features, selectedRole)
  const allowedPageIdSet = new Set(allowedPageIds)
  const defaultRole = getDefaultRole(features)
  const landingPageId =
    (selectedRole && features?.roles[selectedRole]?.landing_page) ??
    (defaultRole ? features?.roles[defaultRole]?.landing_page : null) ??
    null

  const landingFromRole = navigationPages.find(
    (page) => page.id === landingPageId && allowedPageIdSet.has(page.id),
  )
  if (landingFromRole) {
    return landingFromRole.route
  }

  const firstAllowed = navigationPages.find((page) => allowedPageIdSet.has(page.id))
  return firstAllowed?.route ?? '/dashboard'
}

export function isRouteAllowed(
  domainConfig: DomainConfig | undefined,
  features: DomainFeatures | undefined,
  selectedRole: string | null,
  pathname: string,
) {
  return getRouteBlockReason(domainConfig, features, selectedRole, pathname) === null
}

/**
 * Why a path is refused, so `RouteNotAvailable` can tell the user the truth:
 * - `'role'` — the active pack enables this page, but the current role does not
 *   include it. Switching roles may unblock it.
 * - `'pack'` — the active pack does not enable this page at all. No role in
 *   this pack can open it; the answer is to switch packs or edit the pack.
 * - `null` — the route is allowed (or nothing we have an opinion on).
 */
export type RouteBlockReason = 'role' | 'pack'

export function getRouteBlockReason(
  domainConfig: DomainConfig | undefined,
  features: DomainFeatures | undefined,
  selectedRole: string | null,
  pathname: string,
): RouteBlockReason | null {
  if (!features) {
    return null
  }

  const navigationPages = domainConfig?.ui?.navigation?.pages ?? []
  const enabledPages = new Set(features.enabled_pages)
  const allowedPageIds = new Set(getAllowedPageIds(features, selectedRole))

  const normalizedPath = normalizePath(pathname)
  const matchedPage = navigationPages.find((page) => {
    const route = normalizePath(page.route)
    return normalizedPath === route || normalizedPath.startsWith(`${route}/`)
  })

  const pageId = matchedPage?.id ?? packPageIdForPath(normalizedPath)
  if (pageId === null) {
    return null
  }
  if (allowedPageIds.has(pageId)) {
    return null
  }
  return enabledPages.has(pageId) ? 'role' : 'pack'
}