import { Database, FileText } from 'lucide-react'

import type { IngestionSourceType } from '../../lib/ingestion/types'
import './ingestion.css'

type SourceTypeStepProps = {
  selectedSourceType: IngestionSourceType | null
  onChange: (sourceType: IngestionSourceType) => void
}

const sourceOptions: Array<{
  id: IngestionSourceType
  title: string
  description: string
  Icon: typeof FileText
}> = [
  {
    id: 'documents',
    title: 'Documents',
    description: 'Upload source files for document ingestion.',
    Icon: FileText,
  },
  {
    id: 'records',
    title: 'Structured Records',
    description: 'Import tabular rows into a configured record feed.',
    Icon: Database,
  },
]

export function SourceTypeStep({ selectedSourceType, onChange }: SourceTypeStepProps) {
  return (
    <div className="ingestion-source-choice" role="group" aria-label="Source type">
      {sourceOptions.map(({ id, title, description, Icon }) => {
        const isSelected = selectedSourceType === id

        return (
          <button
            key={id}
            type="button"
            className={[
              'ingestion-source-choice__button',
              isSelected ? 'ingestion-source-choice__button--selected' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            aria-pressed={isSelected}
            onClick={() => onChange(id)}
          >
            <span className="ingestion-source-choice__icon" aria-hidden="true">
              <Icon size={20} strokeWidth={2.2} />
            </span>
            <span className="ingestion-source-choice__content">
              <span className="ingestion-source-choice__title">{title}</span>
              <span className="ingestion-source-choice__description">{description}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
