import type { DomainConfig, DomainFeatures } from '../api/contracts'

export function getDefaultRole(features?: DomainFeatures) {
  if (!features) {
    return null
  }

  return features.default_role ?? Object.keys(features.roles)[0] ?? null
}

export function getAllowedPageIds(
  features: DomainFeatures | undefined,
  selectedRole: string | null,
) {
  if (!features) {
    return [] as string[]
  }

  const enabledPages = new Set(features.enabled_pages)
  if (!selectedRole || !features.roles[selectedRole]) {
    return [...enabledPages]
  }

  return features.roles[selectedRole].pages.filter((pageId) => enabledPages.has(pageId))
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
  if (!features) {
    return true
  }

  const navigationPages = domainConfig?.ui?.navigation?.pages ?? []
  const allowedPageIds = new Set(getAllowedPageIds(features, selectedRole))

  const normalizedPath = pathname.endsWith('/') && pathname !== '/' ? pathname.slice(0, -1) : pathname
  const matchedPage = navigationPages.find((page) => {
    const route = page.route.endsWith('/') && page.route !== '/' ? page.route.slice(0, -1) : page.route
    return normalizedPath === route || normalizedPath.startsWith(`${route}/`)
  })

  if (!matchedPage) {
    return true
  }

  return allowedPageIds.has(matchedPage.id)
}