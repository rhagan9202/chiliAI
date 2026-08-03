import { Chip } from '../ui/Chip'
import type { ChipTone } from '../ui/chipTones'
import type { FraudTypologyResponse } from '../../api/contracts'

type TypologyBadgeProps = {
  typology: FraudTypologyResponse
}

const severityTone: Record<NonNullable<FraudTypologyResponse['severity_hint']>, ChipTone> = {
  low: 'success',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
}

function titleForTypology(typology: FraudTypologyResponse): string | undefined {
  if (!typology.description && !typology.severity_hint) return undefined
  const severity = typology.severity_hint
    ? `${typology.severity_hint[0].toUpperCase()}${typology.severity_hint.slice(1)} severity`
    : 'Typology'
  return typology.description ? `${severity}: ${typology.description}` : severity
}

export function TypologyBadge({ typology }: TypologyBadgeProps) {
  return (
    <Chip
      label={typology.label}
      title={titleForTypology(typology)}
      tone={typology.severity_hint ? severityTone[typology.severity_hint] : 'default'}
    />
  )
}
