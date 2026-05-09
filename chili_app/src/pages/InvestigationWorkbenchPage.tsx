import { useParams } from 'react-router-dom'

import { PagePlaceholder } from './PagePlaceholder'
import './pages.css'

export function InvestigationWorkbenchPage() {
  const { entityId } = useParams()

  return (
    <PagePlaceholder eyebrow="Entity workbench" title="Investigation Workbench">
      <p>
        The investigation workbench will replace the provider-specific prototype with a generic
        entity evidence, network, timeline, policy analysis, and feedback surface.
      </p>
      {entityId ? <p>Selected entity route parameter: {entityId}</p> : null}
    </PagePlaceholder>
  )
}