import type { InstallationBranch } from './installationMapGeometry'
import {
  hasActiveHousingFilters,
  INSTALLATION_BRANCHES,
  INSTALLATION_STATUSES,
  type HousingFilterState,
  type InstallationStatus,
} from './housingFilters'

type HousingFilterStripProps = {
  commands: string[]
  filters: HousingFilterState
  matchCount: number
  totalCount: number
  onToggleBranch: (branch: InstallationBranch) => void
  onToggleCommand: (command: string) => void
  onToggleStatus: (status: InstallationStatus) => void
  onClear: () => void
}

type ToggleRowProps<T extends string> = {
  label: string
  options: readonly T[]
  selected: T[]
  onToggle: (value: T) => void
}

function ToggleRow<T extends string>({ label, options, selected, onToggle }: ToggleRowProps<T>) {
  return (
    <div aria-label={label} className="housing-filter-group" role="group">
      <span className="housing-filter-group__label">{label}</span>
      {options.map((option) => (
        <button
          aria-pressed={selected.includes(option)}
          className="housing-filter-toggle"
          key={option}
          onClick={() => onToggle(option)}
          type="button"
        >
          {option}
        </button>
      ))}
    </div>
  )
}

export function HousingFilterStrip({
  commands,
  filters,
  matchCount,
  totalCount,
  onToggleBranch,
  onToggleCommand,
  onToggleStatus,
  onClear,
}: HousingFilterStripProps) {
  const filtersActive = hasActiveHousingFilters(filters)

  return (
    <section aria-label="Installation filters" className="housing-filter-strip">
      <ToggleRow
        label="Filter by status"
        onToggle={onToggleStatus}
        options={INSTALLATION_STATUSES}
        selected={filters.statuses}
      />
      <ToggleRow
        label="Filter by branch"
        onToggle={onToggleBranch}
        options={INSTALLATION_BRANCHES}
        selected={filters.branches}
      />
      {commands.length > 0 ? (
        <ToggleRow
          label="Filter by command"
          onToggle={onToggleCommand}
          options={commands}
          selected={filters.commands}
        />
      ) : null}
      <div className="housing-filter-strip__meta">
        <span aria-live="polite">
          {filtersActive
            ? `Showing ${matchCount} of ${totalCount} installations`
            : `Showing all ${totalCount} installations`}
        </span>
        {filtersActive ? (
          <button className="housing-filter-clear" onClick={onClear} type="button">
            Clear filters
          </button>
        ) : null}
      </div>
    </section>
  )
}
