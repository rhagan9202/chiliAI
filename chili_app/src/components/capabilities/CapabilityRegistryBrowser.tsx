import { useCapabilityRegistry } from '../../api/capabilities'
import type { CapabilityManifestResponse } from '../../api/contracts'
import type { KnowledgeBaseSummaryResponse } from '../../api/contracts'
import { Card } from '../ui/Card'
import { ErrorState } from '../ui/ErrorState'
import { LoadingState } from '../ui/LoadingState'
import './capabilities.css'

type CapabilityRegistryBrowserProps = {
  knowledgeBase: KnowledgeBaseSummaryResponse | null
}

function propertyNames(schema: Record<string, unknown>): string[] {
  const properties = schema.properties
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) {
    return []
  }
  return Object.keys(properties)
}

function listOrDash(values: string[]) {
  return values.length > 0 ? values.join(', ') : 'Any'
}

function auditLabel(capability: CapabilityManifestResponse) {
  return capability.permission.requires_audit ? 'Audit required' : 'No audit'
}

function CapabilityRow({ capability }: { capability: CapabilityManifestResponse }) {
  const inputFields = propertyNames(capability.input_schema)
  const outputFields = propertyNames(capability.output_schema)
  const examples = capability.examples ?? []

  return (
    <article className="capability-row">
      <div className="capability-row__main">
        <div>
          <h3>{capability.label}</h3>
          <p>{capability.description}</p>
        </div>
        <div className="capability-row__chips">
          <span>{capability.side_effect_class}</span>
          <span>{capability.health.status}</span>
          <span>{auditLabel(capability)}</span>
        </div>
      </div>
      <dl className="capability-row__meta">
        <div>
          <dt>Capability</dt>
          <dd>{capability.capability_id}</dd>
        </div>
        <div>
          <dt>Module</dt>
          <dd>{capability.module}</dd>
        </div>
        <div>
          <dt>Roles</dt>
          <dd>{listOrDash(capability.permission.required_roles ?? [])}</dd>
        </div>
        <div>
          <dt>Domains</dt>
          <dd>{listOrDash(capability.domain_compatibility.supported_domains ?? [])}</dd>
        </div>
        <div>
          <dt>Input</dt>
          <dd>{listOrDash(inputFields)}</dd>
        </div>
        <div>
          <dt>Output</dt>
          <dd>{listOrDash(outputFields)}</dd>
        </div>
      </dl>
      {examples.length > 0 ? (
        <details className="capability-row__examples" open>
          <summary>Examples</summary>
          <ul>
            {examples.map((example) => (
              <li key={example.name}>{example.name}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </article>
  )
}

export function CapabilityRegistryBrowser({ knowledgeBase }: CapabilityRegistryBrowserProps) {
  const registry = useCapabilityRegistry(knowledgeBase?.id ?? null)
  const capabilities = registry.data?.items ?? []

  if (!knowledgeBase) {
    return (
      <Card className="capability-browser" compact>
        <p className="page-copy-block">No in-domain knowledge base is available.</p>
      </Card>
    )
  }

  if (registry.isLoading) {
    return <LoadingState label="Loading capability registry" />
  }

  if (registry.isError) {
    return (
      <ErrorState description="The capability registry could not be loaded for this knowledge base." />
    )
  }

  return (
    <div data-testid="capability-registry-browser">
      <Card className="capability-browser" compact>
        <div className="capability-browser__header">
          <div>
            <div className="section-header__eyebrow">Active knowledge base</div>
            <h2>{knowledgeBase.name}</h2>
          </div>
          <strong>{capabilities.length}</strong>
        </div>
        <div className="capability-browser__list">
          {capabilities.length > 0 ? (
            capabilities.map((capability) => (
              <CapabilityRow capability={capability} key={capability.capability_id} />
            ))
          ) : (
            <p className="page-copy-block">No registered capabilities are available.</p>
          )}
        </div>
      </Card>
    </div>
  )
}
