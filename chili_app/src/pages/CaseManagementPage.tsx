import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function CaseManagementPage() {
  return (
    <PagePlaceholder eyebrow="Human feedback loop" title="Case Management">
      <p>
        Case management will capture structured suspicious, not suspicious, and insufficient
        evidence feedback while preserving audit-safe triage-support language.
      </p>
    </PagePlaceholder>
  )
}