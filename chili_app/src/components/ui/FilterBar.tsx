import './ui.css'

export type FilterOption = {
  id: string
  label: string
}

type FilterBarProps = {
  activeFilterId: string
  filters: FilterOption[]
  onChange: (filterId: string) => void
}

export function FilterBar({ activeFilterId, filters, onChange }: FilterBarProps) {
  return (
    <div className="filter-bar" aria-label="Filters">
      {filters.map((filter) => {
        const active = filter.id === activeFilterId
        return (
          <button
            className={active ? 'filter-bar__button filter-bar__button--active' : 'filter-bar__button'}
            key={filter.id}
            onClick={() => onChange(filter.id)}
            type="button"
          >
            {filter.label}
          </button>
        )
      })}
    </div>
  )
}