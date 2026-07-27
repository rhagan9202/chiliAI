export interface UnknownRouteCopy {
  title: string
  description: string
}

/**
 * The catch-all route serves two very different situations and used to explain
 * only one of them. A domain pack can declare a page the SPA has not built yet;
 * far more often the address is simply wrong, and telling that user their URL
 * "is registered in the active domain config" is both confusing and untrue.
 */
export function describeUnknownRoute(
  pathname: string,
  configuredRoutes: readonly string[],
): UnknownRouteCopy {
  const isConfigured = configuredRoutes.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  )

  if (isConfigured) {
    return {
      title: 'Not available yet',
      description:
        'This page is part of the active workspace but has not been built yet. It will appear here once it ships.',
    }
  }

  return {
    title: 'Page not found',
    description: `There is nothing at ${pathname}. Check the address, or pick a destination from the sidebar.`,
  }
}
