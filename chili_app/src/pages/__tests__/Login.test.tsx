import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_BASE_URL } from '../../lib/apiClient'
import { Login } from '../Login'

describe('Login', () => {
  let originalLocation: Location
  let assignMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    originalLocation = window.location
    assignMock = vi.fn()
    // jsdom exposes window.location as non-configurable in some versions, so
    // replace it with a plain object to assert the redirect target.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).location
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { assign: assignMock },
    })
  })

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    })
    vi.restoreAllMocks()
  })

  it('renders sign-in copy and redirects to the backend auth endpoint', () => {
    render(<Login />)

    expect(screen.getByRole('heading', { name: 'chiliAI' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(assignMock).toHaveBeenCalledWith(`${API_BASE_URL}/auth/login`)
  })
})
