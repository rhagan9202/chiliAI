import { formatFileSize } from '../status/formatters'
import './ingestion.css'

type DocumentSourcePanelProps = {
  files: File[]
  onFilesChange: (files: File[]) => void
}

type DirectoryFile = File & { webkitRelativePath?: string }

function fileLabel(file: DirectoryFile): string {
  return file.webkitRelativePath && file.webkitRelativePath.length > 0
    ? file.webkitRelativePath
    : file.name
}

export function DocumentSourcePanel({ files, onFilesChange }: DocumentSourcePanelProps) {
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
          className="ingestion-document-source__input"
          type="file"
          multiple
          aria-label="Document files"
          onChange={(event) => {
            onFilesChange(Array.from(event.currentTarget.files ?? []))
          }}
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
          onChange={(event) => {
            onFilesChange(Array.from(event.currentTarget.files ?? []))
          }}
        />
      </label>

      {files.length > 0 ? (
        <ul className="ingestion-file-list" aria-label="Selected document files">
          {files.map((file) => {
            const label = fileLabel(file as DirectoryFile)
            return (
              <li className="ingestion-file-list__item" key={`${label}-${file.size}`}>
                <span className="ingestion-file-list__name">{label}</span>
                <span className="ingestion-file-list__meta">
                  <span>{file.type || 'unknown type'}</span>
                  <span>{formatFileSize(file.size)}</span>
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}
    </section>
  )
}
