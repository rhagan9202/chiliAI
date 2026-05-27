import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const forbiddenAnalystCopy =
  /seeded investigation graph|seeded RAG service|demo read model/i

describe('analyst-facing page copy', () => {
  it('does not reference seeded or demo-only services in page TSX files', () => {
    const pageFiles = [
      'AlertFeedPage.tsx',
      'CaseManagementPage.tsx',
      'ConfigurationPage.tsx',
      'DashboardPage.tsx',
      'InvestigationWorkbenchPage.tsx',
      'KnowledgeBaseManagerPage.tsx',
      'Login.tsx',
      'PagePlaceholder.tsx',
      'PolicyIntelligencePage.tsx',
      'RagChatPage.tsx',
    ]

    const matches = pageFiles.flatMap((file) => {
      const contents = readFileSync(resolve(__dirname, '..', file), 'utf8')
      const match = contents.match(forbiddenAnalystCopy)
      return match ? [`${file}: ${match[0]}`] : []
    })

    expect(matches).toEqual([])
  })
})
