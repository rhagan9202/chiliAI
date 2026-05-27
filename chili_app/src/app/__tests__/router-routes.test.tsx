import { describe, expect, it } from 'vitest'
import { Navigate } from 'react-router-dom'

import { router } from '../router'

describe('router routes', () => {
  it('keeps the canonical knowledge-bases route and redirects stale knowledgebases links', () => {
    const shellRoute = router.routes.find((route) => route.path === '/')

    expect(shellRoute?.children?.some((route) => route.path === 'knowledge-bases')).toBe(true)

    const staleRoute = shellRoute?.children?.find((route) => route.path === 'knowledgebases')
    expect(staleRoute).toBeDefined()
    expect(staleRoute?.element).toEqual(<Navigate to="/knowledge-bases" replace />)
  })
})
