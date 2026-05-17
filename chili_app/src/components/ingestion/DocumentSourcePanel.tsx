import './ingestion.css'

type DocumentSourcePanelProps = {
  files: File[]
  onFilesChange: (files: File[]) => void
}

function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`
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
        <span className="ingestion-source-panel__label">Document files</span>
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

      {files.length > 0 ? (
        <ul className="ingestion-file-list" aria-label="Selected document files">
          {files.map((file) => (
            <li className="ingestion-file-list__item" key={`${file.name}-${file.size}`}>
              <span className="ingestion-file-list__name">{file.name}</span>
              <span className="ingestion-file-list__meta">
                <span>{file.type || 'unknown type'}</span>
                <span>{formatFileSize(file.size)}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
