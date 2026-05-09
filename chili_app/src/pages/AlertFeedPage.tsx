import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function AlertFeedPage() {
  return (
    <PagePlaceholder eyebrow="Triage queue" title="Alert Feed">
      <p>
        The alert feed will rebuild the prototype anomaly queue as a domain-generic,
        server-backed triage list with filters, assignments, status actions, and reason codes.
      </p>
    </PagePlaceholder>
  )
}