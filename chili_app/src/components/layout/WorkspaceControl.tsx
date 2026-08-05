import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'

import type {
  KnowledgeBaseReadinessResponse,
  KnowledgeBaseSummaryResponse,
  ReadinessIssueResponse,
} from '../../api/contracts'

type WorkspaceControlProps = {
  activeKnowledgeBaseId: string | null
  isError: boolean
  isLoading: boolean
  knowledgeBases: KnowledgeBaseSummaryResponse[]
  onSelectKnowledgeBase: (id: string) => void
  readiness: KnowledgeBaseReadinessResponse | undefined
  readinessError: boolean
  readinessLoading: boolean
}

function readinessLabel({
  activeKnowledgeBaseId,
  readiness,
  readinessError,
  readinessLoading,
}: Pick<
  WorkspaceControlProps,
  'activeKnowledgeBaseId' | 'readiness' | 'readinessError' | 'readinessLoading'
>): string {
  if (!activeKnowledgeBaseId) return 'No KB'
  if (readinessLoading) return 'Checking'
  if (readinessError) return 'Unknown'
  if (!readiness) return 'Unknown'
  return readiness.ready ? 'Ready' : 'Blocked'
}

function readinessTone({
  activeKnowledgeBaseId,
  readiness,
  readinessError,
  readinessLoading,
}: Pick<
  WorkspaceControlProps,
  'activeKnowledgeBaseId' | 'readiness' | 'readinessError' | 'readinessLoading'
>): 'ready' | 'blocked' | 'unknown' {
  if (!activeKnowledgeBaseId || readinessLoading || readinessError || !readiness) {
    return 'unknown'
  }
  return readiness.ready ? 'ready' : 'blocked'
}

function readinessIcon(tone: 'ready' | 'blocked' | 'unknown') {
  if (tone === 'ready') return <CheckCircle2 aria-hidden="true" size={14} />
  if (tone === 'blocked') return <AlertTriangle aria-hidden="true" size={14} />
  return <Loader2 aria-hidden="true" size={14} />
}

function issues(readiness: KnowledgeBaseReadinessResponse | undefined): ReadinessIssueResponse[] {
  if (!readiness) return []
  return [...readiness.blockers, ...readiness.warnings]
}

export function WorkspaceControl({
  activeKnowledgeBaseId,
  isError,
  isLoading,
  knowledgeBases,
  onSelectKnowledgeBase,
  readiness,
  readinessError,
  readinessLoading,
}: WorkspaceControlProps) {
  const hasKnowledgeBases = knowledgeBases.length > 0
  const selectedValue = activeKnowledgeBaseId ?? ''
  const tone = readinessTone({
    activeKnowledgeBaseId,
    readiness,
    readinessError,
    readinessLoading,
  })
  const label = readinessLabel({
    activeKnowledgeBaseId,
    readiness,
    readinessError,
    readinessLoading,
  })
  const readinessIssues = issues(readiness)

  return (
    <div className="workspace-control" data-testid="workspace-control">
      <label className="workspace-control__selector">
        <span className="app-topbar__search-label">Active knowledge base</span>
        <select
          aria-label="Active knowledge base"
          className="workspace-control__select"
          disabled={isLoading || isError || !hasKnowledgeBases}
          onChange={(event) => onSelectKnowledgeBase(event.target.value)}
          value={selectedValue}
        >
          {!activeKnowledgeBaseId ? (
            <option value="">Select a knowledge base</option>
          ) : null}
          {knowledgeBases.map((knowledgeBase) => (
            <option key={knowledgeBase.id} value={knowledgeBase.id}>
              {knowledgeBase.name}
            </option>
          ))}
        </select>
      </label>
      <details className="workspace-control__readiness" data-tone={tone}>
        <summary data-testid="workspace-readiness-status">
          {readinessIcon(tone)}
          {hasKnowledgeBases ? label : 'No knowledge base selected'}
        </summary>
        <div className="workspace-control__details" data-testid="workspace-readiness-details">
          {!hasKnowledgeBases ? (
            <p>Select or create a knowledge base to view readiness.</p>
          ) : readinessIssues.length > 0 ? (
            <ul>
              {readinessIssues.map((issue) => (
                <li key={`${issue.component}:${issue.code}`}>
                  <span>{issue.message}</span>
                  {issue.action ? <strong>{issue.action}</strong> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p>{readiness?.components.knowledge_base?.summary ?? 'Readiness unavailable'}</p>
          )}
        </div>
      </details>
    </div>
  )
}
