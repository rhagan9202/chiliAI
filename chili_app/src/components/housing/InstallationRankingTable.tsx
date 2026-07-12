import type { HousingInstallationResponse } from '../../api/contracts'
import { Chip } from '../ui/Chip'

type InstallationRankingTableProps = {
  installations: HousingInstallationResponse[]
  referenceMode?: boolean
  selectedInstallationId: string | null
  onSelectInstallation: (installationId: string) => void
}

const STATUS_RANK: Record<HousingInstallationResponse['status'], number> = {
  critical: 0,
  watch: 1,
  unknown: 2,
  ok: 3,
}

function statusTone(status: HousingInstallationResponse['status']) {
  switch (status) {
    case 'ok':
      return 'success' as const
    case 'watch':
      return 'warning' as const
    case 'critical':
      return 'danger' as const
    case 'unknown':
      return 'default' as const
  }
}

function formatPercent(value: number | null | undefined) {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`
}

export function InstallationRankingTable({
  installations,
  referenceMode = false,
  selectedInstallationId,
  onSelectInstallation,
}: InstallationRankingTableProps) {
  const rankedInstallations = [...installations].sort((left, right) => {
    const statusDelta = STATUS_RANK[left.status] - STATUS_RANK[right.status]
    if (statusDelta !== 0) {
      return statusDelta
    }
    return right.open_work_orders - left.open_work_orders
  })

  return (
    <div className="housing-table-wrap">
      <table className="housing-table">
        <thead>
          <tr>
            <th scope="col">Installation</th>
            <th scope="col">{referenceMode ? 'Feed status' : 'Status'}</th>
            <th scope="col">Open WOs</th>
            <th scope="col">Occupancy</th>
          </tr>
        </thead>
        <tbody>
          {rankedInstallations.map((installation) => (
            <tr
              className={
                installation.installation_id === selectedInstallationId
                  ? 'housing-table__row housing-table__row--active'
                  : 'housing-table__row'
              }
              key={installation.installation_id}
            >
              <td>
                <button
                  className="housing-table__button"
                  onClick={() => onSelectInstallation(installation.installation_id)}
                  type="button"
                >
                  <strong>{installation.name}</strong>
                  <span>
                    {[installation.majcom, installation.state].filter(Boolean).join(' / ') || 'Unassigned'}
                  </span>
                </button>
              </td>
              <td>
                <Chip
                  label={referenceMode ? 'unscored' : installation.status}
                  tone={referenceMode ? 'default' : statusTone(installation.status)}
                />
              </td>
              <td>{referenceMode ? 'pending' : installation.open_work_orders}</td>
              <td>{referenceMode ? 'pending' : formatPercent(installation.occupancy_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
