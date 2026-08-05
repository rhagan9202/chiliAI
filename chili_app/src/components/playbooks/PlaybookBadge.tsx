import { Chip } from '../ui/Chip'
import type { ChipTone } from '../ui/chipTones'

type PlaybookBadgeProps = {
  status?: string
  title: string
  version: string
}

const STATUS_TONES: Record<string, ChipTone> = {
  draft: 'warning',
  published: 'success',
  retired: 'default',
}

export function PlaybookBadge({ status, title, version }: PlaybookBadgeProps) {
  return (
    <div aria-label="Playbook" className="metric-row metric-row--stacked" role="group">
      <span className="metric-row__label">Playbook</span>
      <strong>{title}</strong>
      <div className="alert-row-card__meta">
        <Chip label={version} tone="network" />
        {status ? <Chip label={status} tone={STATUS_TONES[status] ?? 'default'} /> : null}
      </div>
    </div>
  )
}
