import type {
  EntityFeatureValueResponse,
  FeatureCatalogResponse,
  FeatureDefinitionResponse,
  FraudTypologyResponse,
} from '../../api/contracts'
import { EmptyState } from '../ui/EmptyState'
import { TypologyBadge } from './TypologyBadge'
import './analytics.css'

type FeatureListProps = {
  catalog: FeatureCatalogResponse | null
  values: EntityFeatureValueResponse[]
}

function labelFromId(id: string): string {
  return id.replace(/_/g, ' ')
}

function formatValue(value: EntityFeatureValueResponse['value']): string {
  if (value === null || value === undefined) return 'Raw value unavailable'
  return `Raw value ${String(value)}`
}

function formatNormalizedValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'Not normalized'
  return `${Math.round(value * 100)}%`
}

function indexById<T extends { id: string }>(items: T[]): Map<string, T> {
  return new Map(items.map((item) => [item.id, item]))
}

function typologiesForFeature(
  feature: FeatureDefinitionResponse | undefined,
  typologyIndex: Map<string, FraudTypologyResponse>,
): FraudTypologyResponse[] {
  return (feature?.typology_ids ?? [])
    .map((id) => typologyIndex.get(id))
    .filter((typology): typology is FraudTypologyResponse => Boolean(typology))
}

export function FeatureList({ catalog, values }: FeatureListProps) {
  if (values.length === 0) {
    return (
      <EmptyState
        title="No feature values"
        description="This entity does not have scored feature values yet."
      />
    )
  }

  const featureIndex = indexById(catalog?.features ?? [])
  const typologyIndex = indexById(catalog?.typologies ?? [])

  return (
    <div className="feature-list" data-testid="feature-list">
      {values.map((value) => {
        const feature = featureIndex.get(value.feature_id)
        const typologies = typologiesForFeature(feature, typologyIndex)
        const sourceRefs = value.source_refs ?? []
        return (
          <article
            className="feature-list__item"
            key={`${value.feature_id}:${value.transformation_version}:${value.score_run_id ?? 'latest'}`}
          >
            <div className="feature-list__header">
              <div>
                <h3 className="feature-list__title">
                  {feature?.label ?? labelFromId(value.feature_id)}
                </h3>
                {feature?.description ? (
                  <p className="feature-list__description">{feature.description}</p>
                ) : null}
              </div>
              <strong className="feature-list__score">
                {formatNormalizedValue(value.normalized_value)}
              </strong>
            </div>

            {typologies.length > 0 ? (
              <div className="feature-list__typologies" aria-label="Typologies">
                {typologies.map((typology) => (
                  <TypologyBadge key={typology.id} typology={typology} />
                ))}
              </div>
            ) : null}

            <div className="feature-list__meta">
              <span>{formatValue(value.value)}</span>
              <span>Catalog {value.catalog_version}</span>
              <span>Transform {value.transformation_version}</span>
            </div>

            {sourceRefs.length > 0 ? (
              <ul className="feature-list__sources" aria-label="Source references">
                {sourceRefs.map((sourceRef) => (
                  <li key={sourceRef}>{sourceRef}</li>
                ))}
              </ul>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
