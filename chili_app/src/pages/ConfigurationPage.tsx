import { useDomainConfig } from '../api/config'
import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function ConfigurationPage() {
  const domainConfig = useDomainConfig()
  const entityCount = domainConfig.data?.entities.length ?? 0
  const relationshipCount = domainConfig.data?.relationships.length ?? 0

  return (
    <PagePlaceholder eyebrow="Domain configuration" title="Configuration">
      <p>
        This page will render domain entities, relationships, capabilities, alert thresholds,
        and UI navigation metadata from backend configuration.
      </p>
      <ul>
        <li>Entities loaded: {entityCount}</li>
        <li>Relationships loaded: {relationshipCount}</li>
      </ul>
    </PagePlaceholder>
  )
}