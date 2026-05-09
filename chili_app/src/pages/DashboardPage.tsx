import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function DashboardPage() {
  return (
    <PagePlaceholder eyebrow="Phase 1 shell" title="Dashboard">
      <p>
        This page will rebuild the prototype dashboard with KPI cards, alert trends,
        queue health, recovery/risk categories, and recent high-priority alerts.
      </p>
    </PagePlaceholder>
  )
}