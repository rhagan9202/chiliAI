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
    <fieldset className="ingestion-source-choice">
      <legend className="ingestion-source-choice__legend">Source type</legend>
      {sourceOptions.map(({ id, title, description, Icon }) => {
        const isSelected = selectedSourceType === id

        return (
          <label
            key={id}
            className={[
              'ingestion-source-choice__option',
              isSelected ? 'ingestion-source-choice__option--selected' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <input
              className="ingestion-source-choice__input"
              type="radio"
              name="ingestion-source-type"
              value={id}
              checked={isSelected}
              onChange={() => onChange(id)}
            />
            <span className="ingestion-source-choice__icon" aria-hidden="true">
              <Icon size={20} strokeWidth={2.2} />
            </span>
            <span className="ingestion-source-choice__content">
              <span className="ingestion-source-choice__title">{title}</span>
              <span className="ingestion-source-choice__description">{description}</span>
            </span>
          </label>
        )
      })}
    </fieldset>
  )
}
