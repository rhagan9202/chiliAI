import './ui.css'

export interface FilterGroupOption {
  id: string
  label: string
  /** How many results this option would return under the other active filters. */
  count: number
}

interface FilterGroupProps {
  label: string
  options: readonly FilterGroupOption[]
  selected: readonly string[]
  onToggle: (optionId: string) => void
}

/**
 * One filter dimension, multi-select and labeled (UXA-401).
 *
 * Selections within a group are OR; groups combine with AND, which is what
 * makes "critical AND unacknowledged" expressible. Modelled on the Housing
 * page's FILTER BY STATUS / BRANCH / COMMAND strip, which already got this
 * right. Counts are in the accessible name because the number is meaning, not
 * decoration — an option that would return nothing should say so before it is
 * clicked.
 */
export function FilterGroup({ label, options, selected, onToggle }: FilterGroupProps) {
  if (options.length === 0) return null

  return (
    <div aria-label={label} className="filter-group" role="group">
      <span className="filter-group__label">{label}</span>
      {options.map((option) => {
        const active = selected.includes(option.id)
        return (
          <button
            aria-label={`${option.label}, ${option.count} matching`}
            aria-pressed={active}
            className={
              active ? 'filter-bar__button filter-bar__button--active' : 'filter-bar__button'
            }
            key={option.id}
            onClick={() => onToggle(option.id)}
            type="button"
          >
            {option.label}
            <span className="filter-group__count">{option.count}</span>
          </button>
        )
      })}
    </div>
  )
}
