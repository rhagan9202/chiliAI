import { describe, expect, it } from 'vitest'

import { router } from '../router'

/**
 * Every address the authenticated shell serves, with nested section routes
 * flattened onto their parent's path so a workspace section reads the way it
 * is typed into the address bar.
 */
function paths(): string[] {
  const shell = router.routes.find((route) => route.path === '/')
  const children = shell?.children ?? []
  return children.flatMap((child) => {
    const nested = (child.children ?? []).map((grandchild) =>
      grandchild.index ? `${child.path}#index` : `${child.path}/${grandchild.path}`,
    )
    return [child.path ?? '#index', ...nested]
  })
}

describe('router routes', () => {
  it('serves the library and each workspace section', () => {
    expect(paths()).toEqual(
      expect.arrayContaining([
        'knowledge-bases',
        'knowledge-bases/:kbId#index',
        'knowledge-bases/:kbId/add',
        'knowledge-bases/:kbId/data',
        'knowledge-bases/:kbId/runs',
        'knowledge-bases/:kbId/settings',
      ]),
    )
  })

  it('keeps the stale knowledgebases address served', () => {
    // The pre-split address is still in bookmarks and in e-mailed links; it
    // redirects rather than 404s, and it carries its query string across (the
    // `?kb=` in those links is the knowledge base itself).
    expect(paths()).toContain('knowledgebases')
  })
})
