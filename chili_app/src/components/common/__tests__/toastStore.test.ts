import { beforeEach, describe, expect, it } from 'vitest'

import { showToast, useToastStore } from '../toastStore'

describe('toast actions', () => {
  beforeEach(() => {
    useToastStore.getState().clear()
  })

  it('carries an optional link so a toast can reach what it created', () => {
    // Promoting an alert succeeded with a well-worded toast that led nowhere;
    // the artifact the analyst had just made was unreachable (UXA-405).
    showToast('success', 'Promoted to a case.', { label: 'Open case', to: '/cases?case=c-1' })

    const [toast] = useToastStore.getState().toasts
    expect(toast?.action).toEqual({ label: 'Open case', to: '/cases?case=c-1' })
  })

  it('leaves the action absent when none is given', () => {
    showToast('info', 'Nothing to follow.')

    expect(useToastStore.getState().toasts[0]?.action).toBeUndefined()
  })
})
