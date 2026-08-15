import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDialog } from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        title="t"
        body="b"
        confirmLabel="Delete"
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('gates confirm behind typed text', async () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        title="Delete knowledge base"
        body="Deletes 8 documents, 53 entities, and all runs."
        confirmLabel="Delete knowledge base"
        confirmTypedText="Jimmy_Dean"
        destructive
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    )
    const confirm = screen.getByRole('button', { name: 'Delete knowledge base' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByRole('textbox'), 'Jimmy_Dean')
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('states the blast radius and confirms without typing when no text is required', async () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        title="Remove document"
        body="Removes claims.json and its graph and vector artifacts."
        confirmLabel="Remove"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByRole('dialog')).toHaveTextContent('graph and vector artifacts')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('cancels on Escape', async () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        open
        title="t"
        body="b"
        confirmLabel="Remove"
        onConfirm={() => {}}
        onCancel={onCancel}
      />,
    )
    await userEvent.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('focuses cancel on open so the destructive action is never the default', () => {
    render(
      <ConfirmDialog
        open
        title="t"
        body="b"
        confirmLabel="Delete"
        destructive
        onConfirm={() => {}}
        onCancel={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
  })
})
