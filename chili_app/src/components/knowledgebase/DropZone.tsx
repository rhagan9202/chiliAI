import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, KeyboardEvent } from 'react'

import {
  ACCEPTED_DOCUMENT_EXTENSIONS,
  validateDocumentFile,
} from '../../hooks/useKnowledgeBaseDocuments'
import styles from './DropZone.module.css'

export interface DropZoneProps {
  onFile: (file: File) => void
  onValidationError?: (reason: string) => void
  disabled?: boolean
  helperText?: string
}

export function DropZone({
  onFile,
  onValidationError,
  disabled = false,
  helperText,
}: DropZoneProps): React.ReactElement {
  const [active, setActive] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const handleFiles = (files: FileList | null): void => {
    if (!files || files.length === 0) return
    const file = files[0]
    if (!file) return
    const validation = validateDocumentFile(file)
    if (!validation.ok) {
      onValidationError?.(validation.reason ?? 'Invalid file')
      return
    }
    onFile(file)
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault()
    if (disabled) return
    setActive(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault()
    setActive(false)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault()
    setActive(false)
    if (disabled) return
    handleFiles(event.dataTransfer.files)
  }

  const handleClick = (): void => {
    if (disabled) return
    inputRef.current?.click()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (disabled) return
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      inputRef.current?.click()
    }
  }

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>): void => {
    handleFiles(event.target.files)
    event.target.value = ''
  }

  const className = [
    styles.zone,
    active ? styles.zoneActive : '',
    disabled ? styles.zoneDisabled : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-label="Upload document"
      className={className}
      data-testid="drop-zone"
      data-active={active}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      <span aria-hidden="true" className={styles.icon}>
        ⤒
      </span>
      <span className={styles.title}>
        Drop a file here or click to browse
      </span>
      <span className={styles.hint}>
        {helperText ??
          `Supported: ${ACCEPTED_DOCUMENT_EXTENSIONS.join(', ')} · up to 50 MB`}
      </span>
      <input
        ref={inputRef}
        type="file"
        className={styles.hiddenInput}
        accept={ACCEPTED_DOCUMENT_EXTENSIONS.join(',')}
        onChange={handleInputChange}
        disabled={disabled}
      />
    </div>
  )
}
