import { useDomainConfig, useDomainConfigSchema, useDomainFeatures } from '../api/config'
import { ActivePackEditor } from '../components/config/ActivePackEditor'
import { ExpandableCount } from '../components/config/ExpandableCount'
import { SchemaBrowser } from '../components/config/SchemaBrowser'
import { PackSwitcher } from '../components/config/PackSwitcher'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { useSession } from '../contexts/sessionContextValue'
import './pages.css'

/** Capability keys are internal; these are what an operator reads (UXA-301). */
const CAPABILITY_LABELS: Record<string, string> = {
  timeseries: 'Time series',
  gnn: 'Graph clustering',
  risk_scoring: 'Risk scoring',
  rag_chat: 'RAG Chat',
  explainability: 'Explainability',
  peer_stats: 'Peer statistics',
  structured_ingestion: 'Structured ingestion',
}

export function ConfigurationPage() {
  const { user } = useSession()
  // Mirrors the backend RBAC gate on /config/packs|validate|apply|switch
  // (require_role("admin")): only the literal admin role sits at that level.
  const isAdmin = user?.roles.includes('admin') ?? false
  const domainConfig = useDomainConfig()
  const domainFeatures = useDomainFeatures()
  const domainConfigSchema = useDomainConfigSchema()
  const entityLabels = (domainConfig.data?.entities ?? []).map(
    (entity) => entity.display_label || entity.name,
  )
  const relationshipLabels = (domainConfig.data?.relationships ?? []).map(
    (relationship) => relationship.display_label || relationship.name,
  )
  const enabledCapabilities = Object.entries(domainConfig.data?.capabilities ?? {})
    .filter(([, enabled]) => enabled)
    .map(([name]) => CAPABILITY_LABELS[name] ?? name)
  const roleNames = Object.keys(domainConfig.data?.ui?.roles ?? {})
  const navigationLabels = (domainConfig.data?.ui?.navigation?.pages ?? []).map(
    (page) => page.label,
  )

  if (domainConfig.isLoading) {
    return <LoadingState label="Loading domain configuration" />
  }

  if (domainConfig.isError) {
    return (
      <ErrorState
        description="The workspace configuration could not be loaded, so entity, relationship and capability details are unavailable. Try again in a moment."
      />
    )
  }

  return (
    <section className="page-grid">
      <SectionHeader
        eyebrow="Workspace setup"
        subtitle="What this workspace is set up to track: the entity and relationship types it knows, the analysis it can run, and who can see which pages."
        title="Configuration"
      />
      <div className="dashboard-panels">
        <Card>
          <div className="metric-stack">
            {/* Every count opens to the items behind it (UXA-404): the page
                reported "Entities loaded 8" with no way to see which eight. */}
            <ExpandableCount
              items={entityLabels}
              label="Entity types"
              emptyHint="This pack declares no entity types."
            />
            <ExpandableCount
              items={relationshipLabels}
              label="Relationship types"
              emptyHint="This pack declares no relationships."
            />
            <div className="metric-row">
              <span className="metric-row__label">Domain</span>
              <strong>{domainConfig.data?.domain.display_name}</strong>
            </div>
            <div className="metric-row">
              <span className="metric-row__label">Default entity type</span>
              <strong>{domainFeatures.data?.default_entity_type ?? 'Not configured'}</strong>
            </div>
          </div>
        </Card>
        <Card>
          <div className="metric-stack">
            <ExpandableCount
              items={enabledCapabilities}
              label="Analysis enabled"
              emptyHint="No analysis capabilities are switched on for this pack."
            />
            <ExpandableCount
              items={domainFeatures.data?.enabled_pages ?? []}
              label="Enabled pages"
              emptyHint="This pack enables no pages."
            />
          </div>
        </Card>
        <Card>
          <div className="metric-stack">
            <ExpandableCount
              items={roleNames}
              label="Configured roles"
              emptyHint="This pack configures no roles, so every page is open."
            />
            <ExpandableCount
              items={navigationLabels}
              label="Navigation pages"
              emptyHint="This pack configures no navigation."
            />
            {/* Not an ExpandableCount: the names alone answered nothing an
                operator writing a pack asks (UXA-404). */}
            <SchemaBrowser schema={domainConfigSchema.data} />
          </div>
        </Card>
      </div>
      {isAdmin ? (
        <>
          <SectionHeader
            eyebrow="Domain packs"
            subtitle="Retarget the workspace at a different domain. The new pack is checked before it is applied, and navigation, labels and entity types change in place — no reload, no data loss."
            title="Pack switcher"
          />
          <PackSwitcher />
          <SectionHeader
            eyebrow="Active pack"
            subtitle="Check an edit against the full pack definition before anything changes, then re-apply the active pack to put it into effect."
            title="Pack editor"
          />
          <ActivePackEditor />
        </>
      ) : null}
    </section>
  )
}