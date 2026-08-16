import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { WorkspaceTabs } from '../WorkspaceTabs'

function renderTabs(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <WorkspaceTabs knowledgeBaseId="kb-1" />
    </MemoryRouter>,
  )
}

describe('WorkspaceTabs', () => {
  it('offers every section as a link addressed under the knowledge base', () => {
    renderTabs('/knowledge-bases/kb-1')

    const tabs = screen.getByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Overview' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1',
    )
    expect(within(tabs).getByRole('link', { name: 'Add data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/add',
    )
    expect(within(tabs).getByRole('link', { name: 'Data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/data',
    )
    expect(within(tabs).getByRole('link', { name: 'Runs' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/runs',
    )
    expect(within(tabs).getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/settings',
    )
  })

  it('marks only the section on screen as current', () => {
    renderTabs('/knowledge-bases/kb-1/runs')

    const tabs = screen.getByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Runs' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('does not mark Overview as current on another section (requires `end`)', () => {
    renderTabs('/knowledge-bases/kb-1/runs')

    const tabs = screen.getByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Overview' })).not.toHaveAttribute(
      'aria-current',
    )
  })

  it('marks Overview as current at the workspace root', () => {
    renderTabs('/knowledge-bases/kb-1')

    const tabs = screen.getByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Overview' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
