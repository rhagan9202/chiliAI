import type { KeyboardEvent } from 'react'

import './ui.css'

export type TabItem = {
  id: string
  label: string
}

type TabsProps = {
  activeTabId: string
  ariaControlsPrefix?: string
  idPrefix?: string
  onChange: (tabId: string) => void
  tabs: TabItem[]
}

export function Tabs({ activeTabId, ariaControlsPrefix, idPrefix, onChange, tabs }: TabsProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
    const lastIndex = tabs.length - 1
    let nextIndex: number | null = null

    if (event.key === 'ArrowRight') {
      nextIndex = currentIndex === lastIndex ? 0 : currentIndex + 1
    } else if (event.key === 'ArrowLeft') {
      nextIndex = currentIndex === 0 ? lastIndex : currentIndex - 1
    } else if (event.key === 'Home') {
      nextIndex = 0
    } else if (event.key === 'End') {
      nextIndex = lastIndex
    }

    if (nextIndex === null) {
      return
    }

    event.preventDefault()
    onChange(tabs[nextIndex].id)
    const nextButton = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]
    nextButton?.focus()
  }

  return (
    <div className="tabs" role="tablist" aria-label="Section tabs">
      {tabs.map((tab, index) => {
        const active = tab.id === activeTabId
        const tabElementId = idPrefix ? `${idPrefix}-${tab.id}` : undefined
        const panelElementId = ariaControlsPrefix ? `${ariaControlsPrefix}-${tab.id}` : undefined
        return (
          <button
            aria-controls={panelElementId}
            aria-selected={active}
            className={active ? 'tabs__button tabs__button--active' : 'tabs__button'}
            id={tabElementId}
            key={tab.id}
            onKeyDown={(event) => handleKeyDown(event, index)}
            onClick={() => onChange(tab.id)}
            role="tab"
            tabIndex={active ? 0 : -1}
            type="button"
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
