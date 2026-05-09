import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

import { ConfigEditor } from '../ConfigEditor'
import type { DomainConfig } from '../../types/domainConfig'

vi.mock('@uiw/react-codemirror', () => ({
  default: ({
    value,
    onChange,
  }: {
    value: string
    onChange?: (next: string) => void
  }) => (
    <textarea
      data-testid="cm-mock"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      readOnly={onChange === undefined}
    />
  ),
}))

vi.mock('@codemirror/lang-yaml', () => ({
  yaml: () => ({}),
}))

const mockConfig: DomainConfig = {
  schema_version: '1.0',
  domain: {
    name: 'medicare_fraud',
    display_name: 'Medicare Fraud',
    description: 'Test domain',
  },
  entities: [],
  relationships: [],
  capabilities: {
    timeseries: false,
    gnn: false,
    risk_scoring: false,
    rag_chat: false,
    explainability: false,
  },
  ingestion: {
    sources: [],
    chunking: {
      strategy: 'recursive',
      chunk_size: 1000,
      chunk_overlap: 200,
      min_chunk_size: 50,
    },
  },
  alerts: { thresholds: {} },
}

interface Mounted {
  container: HTMLDivElement
  root: Root
  unmount: () => void
}

function mount(node: React.ReactElement): Mounted {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return {
    container,
    root,
    unmount: () => {
      act(() => {
        root.unmount()
      })
      container.remove()
    },
  }
}

async function flush(times = 4): Promise<void> {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

describe('ConfigEditor', () => {
  const realFetch = global.fetch

  beforeEach(() => {
    global.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify(mockConfig), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    ) as typeof fetch
  })

  afterEach(() => {
    global.fetch = realFetch
    vi.restoreAllMocks()
  })

  it('loads config from /config/domain and renders it in the editor', async () => {
    const handle = mount(<ConfigEditor />)
    await flush()

    const editor = handle.container.querySelector(
      '[data-testid="cm-mock"]',
    ) as HTMLTextAreaElement | null
    expect(editor).not.toBeNull()
    expect(editor?.value ?? '').toContain('"domain"')
    expect(editor?.value ?? '').toContain('Medicare Fraud')
    expect(handle.container.textContent ?? '').toContain('Medicare Fraud')
    handle.unmount()
  })

  it('disables Save with the documented tooltip', async () => {
    const handle = mount(<ConfigEditor />)
    await flush()
    const saveButton = handle.container.querySelector(
      '[data-testid="save-config"]',
    ) as HTMLButtonElement | null
    expect(saveButton).not.toBeNull()
    expect(saveButton?.disabled).toBe(true)
    expect(saveButton?.getAttribute('title') ?? '').toContain(
      'save endpoint not yet available',
    )
    handle.unmount()
  })

  it('shows an inline error when the load fails', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'boom' }), {
          status: 500,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    ) as typeof fetch

    const handle = mount(<ConfigEditor />)
    await flush()
    const errorBox = handle.container.querySelector(
      '[data-testid="config-error"]',
    )
    expect(errorBox).not.toBeNull()
    expect(errorBox?.textContent ?? '').toContain('boom')
    handle.unmount()
  })
})
