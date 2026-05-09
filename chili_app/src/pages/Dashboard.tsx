import { KpiCard } from '../components/dashboard/KpiCard'
import kpiStyles from '../components/dashboard/KpiCard.module.css'
import { RecentActivity } from '../components/dashboard/RecentActivity'
import { useDashboardMetrics } from '../hooks/useDashboardMetrics'
import { useDomainConfig } from '../hooks/useDomainConfig'

export function Dashboard(): React.ReactElement {
  const { data, isLoading, error } = useDashboardMetrics()
  const domain = useDomainConfig()

  const errorMessage = error ? error.message : null

  return (
    <section>
      <h1>Dashboard</h1>
      <p style={{ marginTop: 0, color: 'var(--text, #6b6375)' }}>
        {domain.domain.display_name} overview
      </p>
      <div className={kpiStyles.grid} role="list" aria-label="Key metrics">
        <KpiCard
          title="Total Entities"
          value={data?.totalEntities}
          icon="◆"
          loading={isLoading}
          error={errorMessage}
        />
        <KpiCard
          title="Total Relationships"
          value={data?.totalRelationships}
          icon="↔"
          loading={isLoading}
          error={errorMessage}
        />
        <KpiCard
          title="Open Alerts"
          value={data?.openAlerts}
          icon="⚑"
          loading={isLoading}
          error={errorMessage}
        />
        <KpiCard
          title="Active Knowledge Bases"
          value={data?.activeKnowledgeBases}
          icon="⛁"
          loading={isLoading}
          error={errorMessage}
        />
      </div>
      <div style={{ marginTop: 24 }}>
        <RecentActivity />
      </div>
    </section>
  )
}

export default Dashboard
