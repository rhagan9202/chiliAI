import { useState } from 'react'

import type { DomainConfig, RiskScoreResponse, RuntimeEntity } from '../../api/contracts'
import {
  getEntitySubtitle,
  getEntityTitle,
  getEntityTypeLabel,
} from '../../utils/domainDisplay'
import { getEntityProperties } from '../../utils/entityProperties'
import { countLabel } from '../../utils/countLabel'

export interface EntityDossierHeaderProps {
  entity: RuntimeEntity
  config: DomainConfig
  riskScore: RiskScoreResponse | null
  riskUnavailableReason: string | null
  onAskAi: () => void
}

const RISK_COLORS: Record<string, string> = {
  critical: 'var(--c-red)',
  high: 'var(--c-red)',
  medium: 'var(--c-amber)',
  low: 'var(--c-green)',
}

export function EntityDossierHeader({
  entity,
  config,
  riskScore,
  riskUnavailableReason,
  onAskAi,
}: EntityDossierHeaderProps) {
  const subtitle = getEntitySubtitle(entity, config)
  const numeral = riskScore ? Math.round(riskScore.overall_score * 100) : null
  const [showAllProperties, setShowAllProperties] = useState(false)
  const properties = getEntityProperties(entity, config)
  const hiddenCount = properties.filter((property) => !property.featured).length
  const visibleProperties = showAllProperties
    ? properties
    : properties.filter((property) => property.featured)
  return (
    <div className="dossier-header fade-up" data-testid="entity-dossier-header">
      <div className="dossier-header__identity">
        <h2>{getEntityTitle(entity, config)}</h2>
        <span className="flag-label">
          {getEntityTypeLabel(entity.type, config)}
          {subtitle ? ` · ${subtitle}` : ''}
        </span>
        {visibleProperties.length > 0 ? (
          // A definition list, not chips: these are facts to read, and chip
          // styling made them look like filters you could click.
          <dl className="dossier-properties">
            {visibleProperties.map((property) => (
              <div className="dossier-properties__row" key={property.key}>
                <dt className="dossier-properties__label">{property.label}</dt>
                <dd className="dossier-properties__value">{property.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {hiddenCount > 0 && !showAllProperties ? (
          <div>
            <button
              className="page-button page-button--sm page-button--secondary"
              onClick={() => setShowAllProperties(true)}
              type="button"
            >
              {`Show all ${countLabel(properties.length, 'property', 'properties')}`}
            </button>
          </div>
        ) : null}
        <div>
          <button className="page-button page-button--secondary" onClick={onAskAi} type="button">
            Ask AI
          </button>
        </div>
        {riskUnavailableReason ? (
          <span className="flag-label">{riskUnavailableReason}</span>
        ) : null}
      </div>
      {numeral !== null && riskScore ? (
        <div className="dossier-risk">
          <span
            className="dossier-risk__numeral"
            style={{ color: RISK_COLORS[riskScore.risk_level] ?? 'var(--c-text)' }}
          >
            {numeral}
          </span>
          <span className="dossier-risk__label">{riskScore.risk_level} risk</span>
          <div
            aria-label="Composite risk"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={numeral}
            role="meter"
            className="signal-band__bar"
            style={{ width: '72px' }}
          >
            <div
              style={{
                width: `${numeral}%`,
                height: '100%',
                background: RISK_COLORS[riskScore.risk_level] ?? 'var(--c-cyan)',
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
