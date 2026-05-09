import './ui.css'

export type TabItem = {
  id: string
  label: string
}

type TabsProps = {
  activeTabId: string
  onChange: (tabId: string) => void
  tabs: TabItem[]
}

export function Tabs({ activeTabId, onChange, tabs }: TabsProps) {
  return (
    <div className="tabs" role="tablist" aria-label="Section tabs">
      {tabs.map((tab) => {
        const active = tab.id === activeTabId
        return (
          <button
            aria-selected={active}
            className={active ? 'tabs__button tabs__button--active' : 'tabs__button'}
            key={tab.id}
            onClick={() => onChange(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}