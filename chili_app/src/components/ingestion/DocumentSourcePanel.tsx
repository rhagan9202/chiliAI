import type { ChangeEvent } from 'react'

import { formatFileSize } from '../status/formatters'
import './ingestion.css'

type DocumentSourcePanelProps = {
  files: File[]
  onFilesChange: (files: File[]) => void
  /** Content types the active domain pack accepts, offered to the file picker. */
  acceptContentTypes?: string[]
}

type DirectoryFile = File & { webkitRelativePath?: string }

function fileLabel(file: DirectoryFile): string {
  return file.webkitRelativePath && file.webkitRelativePath.length > 0
    ? file.webkitRelativePath
    : file.name
}

/** Identity for staging purposes — File objects are never referentially stable. */
function fileKey(file: File): string {
  return `${fileLabel(file)}:${file.size}:${file.lastModified}`
}

export function DocumentSourcePanel({
  files,
  onFilesChange,
  acceptContentTypes,
}: DocumentSourcePanelProps) {
  /**
   * Picking files adds to the staging list instead of replacing it.
   *
   * Both inputs used to overwrite the staged set wholesale, so choosing a
   * second batch silently discarded the first — and because the input kept its
   * value, re-picking a corrected file of the same name fired no change event
   * at all. Clearing the value after every read fixes the second half.
   */
  function stageMore(event: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.currentTarget.files ?? [])
    event.currentTarget.value = ''
    if (picked.length === 0) {
      return
    }
    const known = new Set(files.map(fileKey))
    onFilesChange([...files, ...picked.filter((file) => !known.has(fileKey(file)))])
  }

  function removeFile(target: File) {
    onFilesChange(files.filter((file) => fileKey(file) !== fileKey(target)))
  }

  return (
    <section className="ingestion-document-source" aria-labelledby="document-source-title">
      <div className="ingestion-source-panel__header">
        <h3 id="document-source-title" className="ingestion-source-panel__title">
          Document source
        </h3>
      </div>

      <label className="ingestion-source-panel__field">
        <span className="ingestion-source-panel__label">Document files (single or multi-select)</span>
        <input
          accept={acceptContentTypes?.join(',')}
          className="ingestion-document-source__input"
          type="file"
          multiple
          aria-label="Document files"
          onChange={stageMore}
        />
      </label>

      <label className="ingestion-source-panel__field">
        <span className="ingestion-source-panel__label">Document folder</span>
        <input
          className="ingestion-document-source__input"
          type="file"
          multiple
          {...{ webkitdirectory: '', directory: '' }}
          aria-label="Document folder"
          onChange={stageMore}
        />
      </label>

      {files.length > 0 ? (
        <ul className="ingestion-file-list" aria-label="Selected document files">
          {files.map((file) => {
            const label = fileLabel(file as DirectoryFile)
            return (
              <li className="ingestion-file-list__item" key={fileKey(file)}>
                <span className="ingestion-file-list__name">{label}</span>
                <span className="ingestion-file-list__meta">
                  <span>{file.type || 'unknown type'}</span>
                  <span>{formatFileSize(file.size)}</span>
                  <button
                    className="page-button page-button--sm page-button--secondary"
                    onClick={() => removeFile(file)}
                    type="button"
                  >
                    Remove {label}
                  </button>
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}
