import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PlaybookBadge } from '../PlaybookBadge'

describe('PlaybookBadge', () => {
  it('shows title, version, and status', () => {
    render(<PlaybookBadge status="published" title="Provider velocity review" version="v2" />)

    const badge = screen.getByRole('group', { name: 'Playbook' })
    expect(within(badge).getByText('Provider velocity review')).toBeInTheDocument()
    expect(within(badge).getByText('v2')).toBeInTheDocument()
    expect(within(badge).getByText('published')).toBeInTheDocument()
  })
})
