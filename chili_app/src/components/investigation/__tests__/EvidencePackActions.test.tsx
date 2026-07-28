import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { EvidencePackActions } from '../EvidencePackActions'

const mocks = vi.hoisted(() => ({
  exportEvidencePack: vi.fn(),
  downloadTextFile: vi.fn(),
  showToast: vi.fn(),
}))

vi.mock('../../../api/evidence', () => ({ exportEvidencePack: mocks.exportEvidencePack }))
vi.mock('../../common/toastStore', () => ({ showToast: mocks.showToast }))
vi.mock('../../../utils/downloadFile', async () => {
  const actual = await vi.importActual<typeof import('../../../utils/downloadFile')>(
    '../../../utils/downloadFile',
  )
  return { ...actual, downloadTextFile: mocks.downloadTextFile }
})

const CASES = [
  { id: 'case-1', title: 'Redwood DME escalation', alert_ids: ['alert-9'] },
  { id: 'case-2', title: 'Second look', alert_ids: [] },
]

describe('EvidencePackActions export', () => {
  beforeEach(() => {
    mocks.exportEvidencePack.mockReset()
    mocks.downloadTextFile.mockReset()
    mocks.showToast.mockReset()
  })

  it('downloads what the API rendered, under the filename it chose', async () => {
    mocks.exportEvidencePack.mockResolvedValue({
      evidence_pack_id: 'ev-1',
      format: 'markdown',
      filename: 'evidence-ev-1.md',
      content: '# Evidence pack ev-1',
    })
    render(<EvidencePackActions evidencePackId="ev-1" knowledgeBaseId="kb-1" />)

    fireEvent.click(screen.getByRole('button', { name: 'Export Markdown' }))

    await waitFor(() => {
      expect(mocks.exportEvidencePack).toHaveBeenCalledWith('ev-1', 'kb-1', 'markdown')
    })
    expect(mocks.downloadTextFile).toHaveBeenCalledWith(
      'evidence-ev-1.md',
      '# Evidence pack ev-1',
      'text/markdown',
    )
  })

  it('requests JSON with the JSON mime type', async () => {
    mocks.exportEvidencePack.mockResolvedValue({
      evidence_pack_id: 'ev-1',
      format: 'json',
      filename: 'evidence-ev-1.json',
      content: '{}',
    })
    render(<EvidencePackActions evidencePackId="ev-1" knowledgeBaseId="kb-1" />)

    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))

    await waitFor(() => {
      expect(mocks.downloadTextFile).toHaveBeenCalledWith(
        'evidence-ev-1.json',
        '{}',
        'application/json',
      )
    })
  })

  it('reports a failed export and writes no file', async () => {
    mocks.exportEvidencePack.mockRejectedValue(new Error('boom'))
    render(<EvidencePackActions evidencePackId="ev-1" knowledgeBaseId="kb-1" />)

    fireEvent.click(screen.getByRole('button', { name: 'Export Markdown' }))

    await waitFor(() => {
      expect(mocks.showToast).toHaveBeenCalledWith('error', 'Could not export this evidence pack.')
    })
    expect(mocks.downloadTextFile).not.toHaveBeenCalled()
  })
})

describe('EvidencePackActions attach', () => {
  beforeEach(() => {
    mocks.exportEvidencePack.mockReset()
    mocks.downloadTextFile.mockReset()
  })

  it('offers no attach control where there is no alert in hand', () => {
    // The workbench shows a pack without an alert; attaching would invent one.
    render(<EvidencePackActions evidencePackId="ev-1" knowledgeBaseId="kb-1" />)

    expect(screen.queryByRole('button', { name: 'Attach to case' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export Markdown' })).toBeInTheDocument()
  })

  it('excludes cases that already hold this alert', () => {
    const onAttach = vi.fn()
    render(
      <EvidencePackActions
        attach={{ alertId: 'alert-9', cases: CASES, isPending: false, onAttach }}
        evidencePackId="ev-1"
        knowledgeBaseId="kb-1"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Attach to case' }))

    const select = screen.getByLabelText('Attach to')
    const options = [...select.querySelectorAll('option')].map((o) => o.textContent)
    // case-1 already holds alert-9; offering it would only produce a 409.
    expect(options).toEqual(['Choose a case…', 'Second look'])
  })

  it('attaches the chosen case', () => {
    const onAttach = vi.fn()
    render(
      <EvidencePackActions
        attach={{ alertId: 'alert-9', cases: CASES, isPending: false, onAttach }}
        evidencePackId="ev-1"
        knowledgeBaseId="kb-1"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Attach to case' }))
    fireEvent.change(screen.getByLabelText('Attach to'), { target: { value: 'case-2' } })

    expect(onAttach).toHaveBeenCalledWith('case-2')
  })

  it('points at promote when there is no case to attach to', () => {
    render(
      <EvidencePackActions
        attach={{ alertId: 'alert-9', cases: [], isPending: false, onAttach: vi.fn() }}
        evidencePackId="ev-1"
        knowledgeBaseId="kb-1"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Attach to case' }))

    expect(screen.getByText(/promote this alert to open the first one/i)).toBeInTheDocument()
  })

  it('says so when every case already holds the alert', () => {
    render(
      <EvidencePackActions
        attach={{
          alertId: 'alert-9',
          cases: [CASES[0]!],
          isPending: false,
          onAttach: vi.fn(),
        }}
        evidencePackId="ev-1"
        knowledgeBaseId="kb-1"
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Attach to case' }))

    expect(screen.getByText(/already holds this alert/i)).toBeInTheDocument()
  })
})
