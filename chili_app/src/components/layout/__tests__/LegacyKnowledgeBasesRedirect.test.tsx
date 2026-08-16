import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { describe, expect, it } from 'vitest'

import { LegacyKnowledgeBasesRedirect } from '../LegacyKnowledgeBasesRedirect'

function renderAt(initialEntry: string) {
  const router = createMemoryRouter(
    [
      { path: '/knowledgebases', element: <LegacyKnowledgeBasesRedirect /> },
      { path: '/knowledge-bases', element: <p>Library</p> },
    ],
    { initialEntries: [initialEntry] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('LegacyKnowledgeBasesRedirect', () => {
  it('sends the bare legacy address to the library', () => {
    const router = renderAt('/knowledgebases')

    expect(screen.getByText('Library')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/knowledge-bases')
  })

  it('carries the query string across, because it named the knowledge base', () => {
    // The redirect this replaced dropped `?kb=`, so every pre-split bookmark
    // landed on whichever corpus the page happened to auto-select.
    const router = renderAt('/knowledgebases?kb=kb-7&document=doc-2')

    expect(router.state.location.pathname).toBe('/knowledge-bases')
    expect(router.state.location.search).toBe('?kb=kb-7&document=doc-2')
  })
})
