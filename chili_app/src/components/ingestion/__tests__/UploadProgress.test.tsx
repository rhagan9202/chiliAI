import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { UploadProgress } from '../UploadProgress'

describe('UploadProgress', () => {
  it('renders nothing when idle with no error', () => {
    const { container } = render(
      <UploadProgress label="Records upload" status="idle" percent={0} onRetry={vi.fn()} />,
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('exposes an accessible progressbar with the current percentage while uploading', () => {
    render(
      <UploadProgress label="Records upload" status="uploading" percent={42} onRetry={vi.fn()} />,
    )

    const bar = screen.getByRole('progressbar', { name: /records upload/i })
    expect(bar).toHaveAttribute('aria-valuenow', '42')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(screen.getByText('42%')).toBeInTheDocument()
  })

  it('shows the error message and a retry button when the upload fails', async () => {
    const onRetry = vi.fn()
    render(
      <UploadProgress
        label="Records upload"
        status="error"
        percent={0}
        error="Network error during upload."
        onRetry={onRetry}
      />,
    )

    expect(screen.getByRole('alert')).toHaveTextContent('Network error during upload.')

    const retry = screen.getByRole('button', { name: /retry/i })
    await userEvent.click(retry)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('does not render a retry button while uploading', () => {
    render(
      <UploadProgress label="Records upload" status="uploading" percent={10} onRetry={vi.fn()} />,
    )

    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })
})
