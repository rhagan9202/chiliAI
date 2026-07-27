import { act, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useUrlSearchDraft } from '../useUrlSearchDraft'

/**
 * Stands in for a page whose search box is URL-backed. `commitDelay` models the
 * router: the "URL" only catches up after the caller yields, which is exactly
 * the window in which a keystroke used to be reverted.
 */
function Harness({ delayMs = 0, urlLags = true }: { delayMs?: number; urlLags?: boolean }) {
  const [url, setUrl] = useState('')
  const [draft, setDraft] = useUrlSearchDraft(
    url,
    (next) => {
      if (urlLags) {
        setTimeout(() => setUrl(next), 5)
      } else {
        setUrl(next)
      }
    },
    delayMs,
  )
  return (
    <div>
      <input aria-label="search" onChange={(e) => setDraft(e.target.value)} value={draft} />
      <span data-testid="url">{url}</span>
      <button onClick={() => setUrl('')} type="button">
        Clear
      </button>
    </div>
  )
}

function type(input: HTMLElement, text: string) {
  // Character by character with no await between: the case that used to drop
  // characters, because each keystroke landed before the URL had caught up.
  for (let i = 1; i <= text.length; i += 1) {
    const value = text.slice(0, i)
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(input, value)
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
  }
}

describe('useUrlSearchDraft', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('keeps every typed character while the URL lags behind', () => {
    vi.useFakeTimers()
    render(<Harness />)
    const input = screen.getByLabelText('search')

    type(input, 'redwood')

    // The bug this hook exists for: the box read "wd".
    expect((input as HTMLInputElement).value).toBe('redwood')

    act(() => {
      vi.runAllTimers()
    })
    expect(screen.getByTestId('url')).toHaveTextContent('redwood')
  })

  it('resyncs when the URL changes from somewhere else', () => {
    render(<Harness urlLags={false} />)
    const input = screen.getByLabelText('search')

    type(input, 'redwood')
    expect((input as HTMLInputElement).value).toBe('redwood')

    act(() => {
      screen.getByRole('button', { name: 'Clear' }).click()
    })

    expect((input as HTMLInputElement).value).toBe('')
  })

  it('commits once after typing stops when a delay is set', () => {
    vi.useFakeTimers()
    render(<Harness delayMs={250} urlLags={false} />)
    const input = screen.getByLabelText('search')

    type(input, 'upcoding')

    // Mid-word: the box is current, the URL has not been written at all.
    expect((input as HTMLInputElement).value).toBe('upcoding')
    expect(screen.getByTestId('url')).toHaveTextContent('')

    act(() => {
      vi.advanceTimersByTime(250)
    })

    expect(screen.getByTestId('url')).toHaveTextContent('upcoding')
  })

  it('commits immediately when no delay is set', () => {
    render(<Harness urlLags={false} />)
    const input = screen.getByLabelText('search')

    type(input, 'ab')

    expect(screen.getByTestId('url')).toHaveTextContent('ab')
  })
})
